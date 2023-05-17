import asyncio
import json
import os
import traceback
import yaml
from typing import List

import markdown
from bs4 import BeautifulSoup, Tag


DIRECTORY_NAME = 'api'

TYPE_MAPPING = {
    'string': 'string',
    'integer': 'integer',
    'float': 'float',
    'boolean': 'boolean',
    'object': 'object'
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
        self.openapi_schema = {
            'openapi': '3.0.0',
            'info': {
                'title': 'Tockto API',
                'version': '0.1.0'
            },
            'paths': {},
            'components': {
                'schemas': {}
            }
        }

    def get_field_name(self, field_name: str):
        return field_name.replace('[]', '').replace('?', '')
    
    def get_parameters(self, soup: BeautifulSoup):
        def get_data(parameter: tuple, soup: BeautifulSoup):
            parameter_data = []

            h4 = soup.find('h4', string=parameter[0])
            if h4 is None:
                return parameter_data

            table = h4.find_next_sibling()
            tbody = table.find('tbody')
            for tr in tbody.find_all('tr'):
                row = [td.text for td in tr.find_all('td')]

                field_name = self.get_field_name(row[0])
                parameter_data.append({
                    'required': False if '?' in row[0] else True,
                    'schema': {
                        'type': TYPE_MAPPING[row[1].lower()],
                    },
                    'name': field_name,
                    'in': parameter[1],
                    'description': row[1],
                })

            return parameter_data
        
        parameter_set = [
            ('Headers', 'header'),
            ('Query', 'query'),
            ('Path', 'path')
        ]
        parameters = []
        for parameter in parameter_set:
            parameter_data = get_data(parameter, soup)
            parameters.extend(parameter_data)

        return parameters
    
    def set_schema(self, base_schema_name: str, table: Tag):
        self.openapi_schema['components']['schemas'][base_schema_name] = {
            "type": "object",
            "required": [],
            "properties": {}
        }

        schemas = self.openapi_schema['components']['schemas']
    
        def get_field_schema(
            part: str,
            field_type: str,
            is_leaf: bool,
            schema_name: str = None
        ):
            if '[]' in part:
                if is_leaf:
                    schema = {
                        'type': 'array',
                        'items': {
                            'type': field_type
                        }
                    }
                else:
                    schema = {
                        'type': 'array',
                        'items': {
                            '$ref': f"#/components/schemas/{schema_name}"
                        }
                    }
            else:
                if is_leaf:
                    schema = {
                        'type': field_type
                    }
                else:
                    schema = {
                        '$ref': f"#/components/schemas/{schema_name}"
                    }
            
            return schema


        tbody = table.find('tbody')
        for tr in tbody.find_all('tr'):
            row = [td.text.strip() for td in tr.find_all('td')]

            schema_name = base_schema_name
            key_parts = row[0].split(".")
            field_type = TYPE_MAPPING[row[1].lower()]
            
            length = len(key_parts)
            for i, part in enumerate(key_parts):
                field_name = self.get_field_name(part)
                if i == length - 1:
                    field_schema = get_field_schema(part, field_type, True)
                else:
                    field_schema = get_field_schema(part, field_type, False, schema_name + field_name.capitalize())


                if schema_name in schemas:
                    schemas[schema_name]["properties"][field_name] = field_schema
                else:
                    schemas[schema_name] = {
                        "type": "object",
                        "required": [],
                        "properties": {
                            field_name: field_schema
                        }
                    }
                
                required = schemas[schema_name]['required']
                if '?' not in part and field_name not in required:
                    required.append(field_name)

                schema_name += field_name.capitalize()

    def get_responses(self, soup: BeautifulSoup, base_schema_name: str):
        response_data = {}
        response_tag = soup.find('h3', string='Responses')
        if response_tag is None:
            return None

        for h4 in response_tag.find_next_siblings('h4'):
            status_code = h4.get_text()
            if status_code[0] == '2':
                description = f'Success {status_code}'
            else:
                description = f'Error {status_code}'

            schemas = {
                'description': description,
            }
            for p in h4.find_next_siblings('p'):
                if p.get_text().lower() == 'content':
                    schema_name = f'{base_schema_name}Response{status_code}Content'
                    schemas['content'] = {
                        'application/json': {
                            'schema': {
                                '$ref': f'#/components/schemas/{schema_name}'
                            }
                        }
                    }
                # else:
                #     schema_name = f'{base_schema_name}Response{status_code}Headers'
                #     schemas['headers'] = {
                #         'application/json': {
                #             'schema': {
                #                 '$ref': f'#/components/schemas/{schema_name}'
                #             }
                #         }
                #     }

                self.set_schema(schema_name, h4.find_next_sibling('table'))

            response_data[status_code] = schemas

        return response_data

    def get_request_body(self, soup: BeautifulSoup, base_schema_name: str):
        schema_name = f'{base_schema_name}RequestBody'
        request_body = {
            'content': {
                'application/json': {
                    'schema': {
                        '$ref': f'#/components/schemas/{schema_name}'
                    }
                }
            },
            'required': True
        }

        h4 = soup.find('h4', string='Body')
        if h4 is None:
            return None

        self.set_schema(schema_name, h4.find_next_sibling('table'))
        
        return request_body
        
    def set_path_data(self, soup: BeautifulSoup):
        method, url = soup.find('h1').get_text().split(' ')
        method = method.lower()

        path_data = {
            'description': soup.find('h2').get_text().replace('description: ', '')
        }
        base_schema_name = f"{method}{url.replace('/', ' ').replace('{', ' ').replace('}', '').replace('_', ' ')}"
        base_schema_name = base_schema_name.title().replace(' ', '')

        parameters = self.get_parameters(soup)
        if parameters:
            path_data['parameters'] = parameters

        responses = self.get_responses(soup, base_schema_name)
        if responses:
            path_data['responses'] = responses

        request_body = self.get_request_body(soup, base_schema_name)
        if request_body:
            path_data['requestBody'] = request_body

        if url in self.openapi_schema['paths']:
            self.openapi_schema['paths'][url][method] = path_data
        else:
            self.openapi_schema['paths'][url] = {method: path_data}

    def convert(self):
        for soup in self.soups:
            try:
                self.set_path_data(soup)
            except Exception as e:
                traceback.print_exc()

        write_yaml_file(self.openapi_schema)

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
    converter.convert()
    

asyncio.run(main())