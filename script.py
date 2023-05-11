import asyncio
import json
import os
import yaml
from typing import List

import markdown
from bs4 import BeautifulSoup, Tag


DIRECTORY_NAME = 'api'

TYPE_MAPPING = {
    'string': 'string',
    'integer': 'integer',
}


def write_json_file(data: dict):
    json_object = json.dumps(data, indent=4)
    with open('test.json', 'w') as f:
        f.write(json_object)
        

def write_yaml_file(data: dict):
    with open('openapi.yaml', 'w') as f:
        yaml.dump(data, f)


class OpenAPIConvert:
    def __init__(self):
        self.soups: List[BeautifulSoup] = []
        self.openapi_data = {
            'openapi': '3.1.0',
            'info': {
                'title': 'Tockto API',
                'version': '0.1.0'
            },
            'paths': {},
            'components': {
                'schemas': {}
            }
        }
    
    def get_parameter_data(self, parameter: tuple, soup: BeautifulSoup):
        parameter_data = []

        h4 = soup.find('h4', string=parameter[0])
        if h4 is None:
            return parameter_data

        table = h4.find_next_sibling()
        tbody = table.find('tbody')
        for tr in tbody.find_all('tr'):
            row = [td.text for td in tr.find_all('td')]
            parameter_data.append({
                'required': True if row[2] == 'Yes'else False,
                'schema': {
                    'type': TYPE_MAPPING[row[1].lower()],
                },
                'name': row[0],
                'in': parameter[1],
                'description': row[3],
            })

        return parameter_data
    
    def get_parameters(self, soup: BeautifulSoup):
        parameter_set = [
            ('Headers', 'header'),
            ('Query', 'query'),
            ('Path', 'path')
        ]
        parameters = []
        for parameter in parameter_set:
            parameter_data = self.get_parameter_data(parameter, soup)
            parameters.extend(parameter_data)

        return parameters
    
    def set_schema(self, schema_name: str, table: Tag):
        required = []
        properties = {}
        tbody = table.find('tbody')
        for tr in tbody.find_all('tr'):
            row = [td.text for td in tr.find_all('td')]
            if row[2] == 'Yes':
                required.append(row[0])

            properties[row[0]] = {
                'title': row[0],
                'type': TYPE_MAPPING[row[1].lower()]
            }

        self.openapi_data['components']['schemas'][schema_name] = {
            'title': schema_name,
            'type': 'object',
            'required': required,
            'properties': properties
        }
    
    def get_responses(self, soup: BeautifulSoup, url: str, method: str):
        response_data = {}

        response_tag = soup.find('h3', string='Responses')
        for h4 in response_tag.find_next_siblings('h4'):
            status_code = h4.get_text()
            schema_name = f"{method}{url.replace('/', ' ')}".title().replace(' ', '')
            if status_code[0] == '2':
                description = f'Success {status_code}'
                schema_name += f'Success{status_code}'
            else:
                description = f'Error {status_code}'
                schema_name += f'Error{status_code}'

            response_data[status_code] = {
                'description': description,
                'content': {
                    'application/json': {
                        'schema': {
                            '$ref': f'#/components/schemas/{schema_name}'
                        }
                    }
                }
            }

            self.set_schema(schema_name, h4.find_next_sibling('table'))

        return response_data
        
    def set_path_data(self, soup: BeautifulSoup):
        method, url = soup.find('h1').get_text().split(' ')
        method = method.lower()

        path_data = {
            'description': soup.find('h2').get_text().replace('description: ', ''),
            'parameters': self.get_parameters(soup),
            'responses': self.get_responses(soup, url, method)
        }

        if url in self.openapi_data['paths']:
            self.openapi_data['paths'][url][method] = path_data
        else:
            self.openapi_data['paths'][url] = {
                method: path_data
            }

    def to_openapi(self):
        for soup in self.soups:
            try:
                self.set_path_data(soup)
            except Exception as e:
                print(e)

        write_yaml_file(self.openapi_data)

    @classmethod
    def read_markdown(cls):
        obj = cls()
        for filename in os.listdir(DIRECTORY_NAME):
            f = os.path.join(DIRECTORY_NAME, filename)
            with open(f, 'r') as file:
                text_markdown = file.read()
                html_string = markdown.markdown(text_markdown, extensions=['tables'])

            obj.soups.append(BeautifulSoup(html_string, 'html.parser'))

        return obj


async def main():
    converter = OpenAPIConvert.read_markdown()
    converter.to_openapi()
    

asyncio.run(main())