import json
import os.path
import re
from abc import ABC, abstractmethod
from requests import get
from pydantic import BaseModel, ValidationError

EXCHANGE_RATE = 80  # курс перевода зарплаты в рубли


class Vacancy:
    """
    Класс вакансии
    """

    all: list = []  # буфер для временного хранения экземпляров вакансий при сортировке и т.д.

    def __init__(self, **attrs) -> None:  # создаем экземпляр с нужными полями
        try:
            self.name: str = attrs['name']  # название вакансии
            self.url: str = attrs['url']  # ссылка на вакансию
            self.req: str = attrs['requirement']  # требования
            self.salary_from: int = attrs['salary_from']  # зп от
            self.salary_to: int = attrs['salary_to']  # зп до
        except KeyError as err:
            raise KeyError(err)

    @property  # геттер для requirement
    def req(self) -> str:
        return self.requirement

    @req.setter  # сеттер для фильтрации requirement
    def req(self, value: str) -> None:
        if value:  # очистка поля requirement от всяких странных символов
            value = value.replace('<highlighttext>', '').replace('</highlighttext>', '')
            regex = r'[^a-zA-Zа-яА-ЯёЁ\d~`!?@№#$%^&*\-+\[\]{}()<>|\/\\.,;:"\'«»–— ]+'
            reg = re.compile(regex)
            self.requirement = reg.sub('', value)
        else:
            self.requirement = ''

    @property  # геттер для методов сравнения
    def salary(self) -> int:
        return self.salary_to if self.salary_to else self.salary_from

    def __str__(self) -> str:
        return f"Сервис: {self.service_name}\n" \
               f"Название вакансии: {self.name}\n" \
               f"Ссылка на вакансию: {self.url}\n" \
               f"Требования: {self.requirement}\n" \
               f"Зарплата: {self.salary_from if self.salary_from else 0} -> " \
               f"{self.salary_to if self.salary_to else ''} руб/мес\n"

    # методы сравнения
    def __gt__(self, other) -> bool:
        return self.salary > other.salary

    def __lt__(self, other) -> bool:
        return self.salary < other.salary

    def __eq__(self, other) -> bool:
        return self.salary == other.salary

    def __ge__(self, other) -> bool:
        return self.salary >= other.salary

    def __le__(self, other) -> bool:
        return self.salary <= other.salary


class VacancyFromJSON:
    """
    Класс mixin для инициализации экземпляра вакансии данными из JSON файла
    """

    def init_from_json(self, data: dict) -> None:
        super().__init__(name=data['name'],  # название вакансии
                         url=data['url'],  # ссылка на вакансию
                         requirement=data['requirement'],  # требования
                         salary_from=data['salary_from'],  # зп от
                         salary_to=data['salary_to'])  # зп до


class HHVacancy(VacancyFromJSON, Vacancy):
    """
    Вакансия HeadHunter
    """

    def __init__(self, data: dict) -> None:
        if data.get('service_name'):  # если создаем из файла
            self.init_from_json(data)
        else:  # если создаем из запроса
            super().__init__(name=data['name'],
                             url=data['alternate_url'],
                             requirement=data['snippet']['requirement'],
                             salary_from=0 if data['salary']['from'] is None else
                             data['salary']['from'] if data['salary']['currency'] == 'RUR'
                             else data['salary']['from'] * EXCHANGE_RATE,
                             salary_to=0 if data['salary']['to'] is None else
                             data['salary']['to'] if data['salary']['currency'] == 'RUR'
                             else data['salary']['to'] * EXCHANGE_RATE)
        self.service_name = "HeadHunter"


class SJVacancy(VacancyFromJSON, Vacancy):
    """
    Вакансия SuperJob
    """

    def __init__(self, data: dict) -> None:
        if data.get('service_name'):  # если создаем из файла
            self.init_from_json(data)  # название вакансии
        else:  # если создаем из запроса
            super().__init__(name=data['profession'],
                             url=data['link'],
                             requirement=data['candidat'],
                             salary_from=0 if data['payment_from'] is None else
                             data['payment_from'] if data['currency'] == 'rub'
                             else data['payment_from'] * EXCHANGE_RATE,
                             salary_to=0 if data['payment_to'] is None else
                             data['payment_to'] if data['currency'] == 'rub'
                             else data['payment_to'] * EXCHANGE_RATE)
        self.service_name = "SuperJob"


class API(ABC):
    """
    Абстрактный класс для создания API
    """

    @abstractmethod
    def get_request(self, keyword):
        pass


class HH(API):
    """
    Класс для работы с API HeadHunter
    """

    url = 'https://api.hh.ru/vacancies'

    def get_page(self, keyword: str, page: int) -> dict:  # получает одну страницу запроса
        params = {
            'text': keyword,
            'area': 113,
            'page': page,
            'per_page': 100,
            'only_with_salary': True,
            'search_field': 'name'
        }
        try:
            response = get(self.url, params).json()
            return response
        except KeyError as err:
            raise KeyError(err)
        except Exception as err:
            raise Exception(err)

    def get_request(self, keyword: str) -> list[dict]:  # формирует запрос, с циклом по числу найденных страниц
        result = []
        print('Идет поиск на HeadHunter...')
        for page in range(10):  # пробуем прочитать 10 страниц по 100 вакансий
            one_page_data = self.get_page(keyword, page)  # получение очередной страницы
            result += one_page_data['items']
            if one_page_data['pages'] - page <= 1: break  # проверка достижения последней страницы поиска
        return result


class SJ(API):
    """
    Класс для работы с API SuperJob
    """

    url = 'https://api.superjob.ru/2.0/vacancies/'
    headers = {
        'X-Api-App-Id':
            'v3.r.137478329.0484df93bd0dbe1d4ec473961f0e68359d16d3f6.0ab6ee7c38c6375a5deb84c35464cc67b7b4c44b'
    }

    def get_page(self, keyword: str, page: int) -> dict:  # получает одну страницу запроса
        params = {
            'keywords': keyword,
            'c': 1,
            'page': page,
            'count': 100
        }
        try:
            response = get(self.url, params=params, headers=self.headers).json()
            return response
        except KeyError as err:
            raise KeyError(err)
        except Exception as err:
            raise Exception(err)

    def get_request(self, keyword: str) -> list[dict]:  # формирует запрос, с циклом по числу найденных страниц
        result = []
        print('Идет поиск на SuperJob...')

        for page in range(10):  # пробуем прочитать 10 страниц по 100 вакансий
            one_page_data = self.get_page(keyword, page)  # получение очередной страницы
            result += one_page_data['objects']
            if not one_page_data['more']: break  # проверка достижения последней страницы поиска
        return result


class FileInterface(ABC):
    """
    Абстрактный класс для работы с файлом
    """

    @abstractmethod
    def insert(self, data):
        pass

    @abstractmethod
    def validation(self):
        pass


class JSONFileInterface(FileInterface):
    """
    Класс для работы с JSON-файлом данных
    """

    def __init__(self, filename: str) -> None:
        self.filename = filename  # при инициализации экземпляра
        if not self.is_file_exists(self.filename):  # проверяем существование файла
            self.datafile = []  # создаем пустой, если не существует

    @property  # геттер, читаем файл
    def datafile(self) -> list[dict] | None:
        with open(self.filename, encoding='utf-8') as file:
            try:  # пробуем преобразовать в JSON
                data = json.load(file)
            except Exception:  # не удалось декодировать JSON
                print('Файл поврежден')
            else:
                return data

    @datafile.setter  # сеттер, пишем файл
    def datafile(self, data: list[dict]) -> None:
        with open(self.filename, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def validation(self) -> bool:  # Проверка JSON-файла
        file_ready = True

        class VacancyStructure(BaseModel):  # шаблон вакансии для валидации
            name: str
            url: str
            requirement: str | None
            salary_from: int | None
            salary_to: int | None
            service_name: str

        data = self.datafile
        if not data:  # файл поврежден или пустой
            print('Требуется загрузка данных')
            file_ready = False
        else:
            for vacancy in data:  # проверка структуры найденного JSON
                try:
                    VacancyStructure.parse_raw(json.dumps(vacancy))
                except ValidationError:
                    print('Неправильная структура данных в файле, требуется перезагрузка данных')
                    file_ready = False
        return file_ready

    def insert(self, data: list[Vacancy]) -> None:  # добавление данных в файл
        result = self.datafile
        for item in data:
            result.append(item.__dict__)
        self.datafile = result

    @staticmethod  # проверка существования файла
    def is_file_exists(filename: str) -> bool:
        return os.path.exists(filename)
