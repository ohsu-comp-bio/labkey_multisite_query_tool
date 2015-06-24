# -*- coding: utf-8 -*-
import os
import requests
from urlparse import urljoin
import pandas as pd
import yaml

class LabKey(object):

    @classmethod
    def from_yaml_file(cls, config_file_path):
        """Return a collection of LabKey instances from a YAML file.

        Args:

            config_file_path (str): Path to a YAML config files.
        """ 

        # Expand environment variables.
        config_file_path = os.path.expandvars(config_file_path)

        # Read our config file. 
        with open(config_file_path, 'r') as config_file:
            config = yaml.load(config_file)
            
        default_config = config['default']

        labkey_instances = []

        for server in config['servers']:

            # Combine our default config with our server config.
            config = default_config.copy()
            config.update(server)

            labkey = LabKey(
                host = config['host'],
                email = config['email'],
                password = config['password'],
                project = config['project'],
                schema = config['schema'],
                query_name = config['query_name'],
                columns = config['columns'],
                aliases = config['aliases'],
                custom_columns = config['custom_columns'],
            )

            labkey_instances.append(labkey)

        return labkey_instances

    def __init__(self,
            host=None,
            email=None,
            password=None,
            project=None,
            schema=None, 
            query_name=None,
            columns=[],
            aliases={},
            custom_columns={},
            ):
        """
        Initialize an instance of a LabKey server connection.
        """

        self.host = host
        self.email = email
        self.password = password
        self.project = project
        self.schema = schema
        self.query_name = query_name
        self.columns = columns
        self.aliases = aliases
        self.custom_columns = custom_columns

        # Create a session object for this LabKey instance.
        self.session = requests.Session()


    def query(self, filters={}, aliases={}):
        """Query a Labkey instance using a collection of filters.

        Args:
            filters (dict): A hash of LabKey-compliant filters.
            aliases (dict): A dict containing column mapping names.

        Examples:

            >>> filters = {
                    "specimen_id/donor_sex~eq": "Male",
                    "specimen_id/donor_age_at_diagnosis~lte": 40
                    }
            >>> df = labkey.query(filters)
        """

        query_url = self.url("query/{0}/selectRows.api".format(self.project))

        # We need to reverse our alias map.
        reverse_aliases = {value: key for key, value in self.aliases.iteritems()}

        # Note that we have to take the column specified by the user (i.e.,
        # "gender" and map it to the original column name (i.e.,
        # "specimen_id/donor_sex").
        columns = [reverse_aliases.get(column, column) for column in self.columns]

        params = {
            "schemaName": self.schema,
            "query.queryName": self.query_name,
            "query.columns": ','.join(columns)
        }

        # Iterate through the filters and prepend 'query.' to each key. Note
        # that we use the reversed_alias so that when a user queries on something
        # like 'gender', we will use the actual column name 'speciman_id/donor_sex'.
        filter_params = {}

        for key, value in filters.iteritems():

            column, operator = key.split("~")

            labkey_column = reverse_aliases.get(column, column)

            expression = "query.{0}~{1}".format(labkey_column, operator)

            filter_params[expression] = value

        # Add our default options to our query params
        params.update(filter_params)

        response = self.session.get(query_url, params=params)

        # If we got an error code, raise an exception.
        response.raise_for_status()

        # Parse the response as JSON.
        response_data = response.json()

        rows = response_data["rows"]

        # Delete rows from our response and use the rest of the response as metadata.
        del response_data["rows"]
        metadata = response_data

        # Read our rows into a Pandas data frame.
        data_frame = pd.DataFrame.from_dict(rows)

        # Attach our metadata to the data frame
        data_frame._metadata = metadata

        # Rename our columns
        data_frame.rename(columns=self.aliases, inplace=True)

        # Add our custom columns.
        for key, value in self.custom_columns.iteritems():
            data_frame[key] = value

        return data_frame


    def login(self, email=None, password=None):
        """Logs into a LabKey instance. Persists JSESSIONID cookie in session.
        
        Args:

            email (string): User e-mail.
            password (string): User passowrd.
        
        Examples:

            >>> labkey.login(email="foo@bar.com", password="foobar")
        """

        if email is None:
            email = self.email

        if password is None:
            password = self.password

        login_url = self.url('login/login.post')

        payload = {
            "email": email,
            "password": password
        }

        response = self.session.post(login_url, data=payload)

        # If we got an error code, raise an exception.
        response.raise_for_status()

        # Verify that we received JSESSIONID within our response.
        if not "JSESSIONID" in self.session.cookies:
            raise RuntimeError("Unable to authenticate.")


    def url(self, relative_url):
        """Create a url using a relative path and the host url.

        Args:

            relative_url (string): Relative URL.

        Examples:

            >>> labkey = LabKey(host="http://localhost:9004/labkey/")
            >>> labkey.url('login/login.post')
            "http://localhost:9004/labkey/login/login.post"
        """
        return urljoin(self.host, relative_url)
