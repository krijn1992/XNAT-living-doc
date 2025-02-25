# xnat_canvas_integration.py

import requests
from tqdm import tqdm
import yaml
import logging
import xml.etree.ElementTree as ET


class CanvasIntegration:
    def __init__(self, canvas_url: str, canvas_token: str):
        """
        Initialize the CanvasIntegration class with the necessary URL and token.

        :param canvas_url: The base URL for the Canvas API.
        :param canvas_token: The token for authenticating with the Canvas API.
        """
        self.canvas_url = canvas_url
        self.canvas_token = canvas_token

    def _request(self, method: str, endpoint: str, params: dict = None) -> requests.Response:
        """
        Make a request to the Canvas API.

        :param method: The HTTP method to use (e.g., 'GET', 'POST').
        :param endpoint: The API endpoint to target.
        :param params: Optional query parameters.
        :return: The response from the API request.
        """
        response = requests.request(method, f"{self.canvas_url}{endpoint}",
                                    headers={'Authorization': f'Bearer {self.canvas_token}'},
                                    params=params
                                    )
        if response.status_code not in [200, 204]:
            logging.error(f"API Error: {response.status_code} - {response.text}")
        return response

    def get_canvas_courses(self):
        """
        Get a list of all courses from Canvas.

        :return: A tuple containing lists of course IDs and course names.
        """
        response = self._request('GET', "/courses")#, params={'enrollment_type': 'teacher'})
        course_ids = [course['id'] for course in response.json()]
        course_names = [course['name'] for course in response.json()]
        # Override outcome for debug
        # course_ids = [12553]
        return course_ids, course_names

    def get_canvas_participants(self, project_id: int) -> list:
        """
        Get a list of participants in a specific Canvas course.

        :param project_id: The ID of the Canvas course.
        :return: A list of participants.
        """
        participants = []
        page = 1

        while True:
            try:
                response = self._request('GET', f"/courses/{project_id}/users", params={'page': page, 'per_page': 100})
                participants.extend(response.json())
                if not response.links.get('next'):
                    break
                page += 1
            except requests.exceptions.RequestException as err:
                # Print an error message if an exception occurs and exit the loop
                print(f"Error occurred: {err}")
                break
        return participants

class XNATIntegration:
    def __init__(self, xnat_url: str, username: str, password: str):
        """
        Initialize the XNATIntegration class with the necessary credentials.

        :param xnat_url: The base URL for the XNAT API.
        :param username: The username for authenticating with the XNAT API.
        :param password: The password for authenticating with the XNAT API.
        """
        self.xnat_url = xnat_url
        self.username = username
        self.password = password
        self.token = ""

    def _init_request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> requests.Response:
        """
        Make an initial request to the XNAT API using basic authentication.

        :param method: The HTTP method to use (e.g., 'GET', 'POST').
        :param endpoint: The API endpoint to target.
        :param data: Optional data payload for the request.
        :param params: Optional query parameters.
        :return: The response from the API request.
        """
        response = requests.request(method, f"{self.xnat_url}{endpoint}",
                                    auth=(self.username, self.password),
                                    json=data, params=params)
        if response.status_code not in [200, 204]:
            logging.error(f"API Error: {response.status_code} - {response.text}")
        return response

    def _request(self, method: str, endpoint: str,add_header:dict = None, data = None, params: dict = None) -> requests.Response:
        """
        Make a request to the XNAT API using a session token.

        :param method: The HTTP method to use (e.g., 'GET', 'POST').
        :param endpoint: The API endpoint to target.
        :param add_header: Optional additional headers.
        :param data: Optional data payload for the request.
        :param params: Optional query parameters.
        :return: The response from the API request.
        """
        headers = {'Cookie': f'JSESSIONID={self.token}'}
        if add_header is not None:
            headers.update(add_header)
        response = requests.request(method, f"{self.xnat_url}{endpoint}",
                                    headers=headers, data=data, params=params)
        if response.status_code not in [200, 204]:
            logging.error(f"API Error: {response.status_code} - {response.text}")
        return response

    def get_user_token(self) -> str:
        """
        Obtain a session token for the XNAT API.

        :return: The session token.
        """
        response = self._init_request('POST', f"/data/JSESSION")
        if response.ok:
            self.token = response.cookies['JSESSIONID']
        return None

    def get_users_in_xnat(self) -> dict:
        """
        Retrieve a list of users from the XNAT system.

        :return: A dictionary of users.
        """
        response = self._request('GET', "/xapi/users")
        if response.ok:
            return response.json()
        return None

    def get_project_ids_list(self) -> list:
        """
        Retrieve a list of project IDs from the XNAT system.

        :return: A list of project IDs.
        """
        response = self._request('GET', f"/data/projects")
        projects = response.json()
        results = projects.get('ResultSet', {}).get('Result', [])
        return [project['ID'] for project in results]

    def create_project(self, xml_string: str):
        """
        Create a new project in the XNAT system.

        :param xml_string: The XML representation of the project data.
        """
        response = self._request('POST', "/data/projects", {"Content-Type": "application/xml"}, data=xml_string)
        # Check the response
        if response.status_code == 200:
            print("Project created successfully!")
        else:
            print(f"Failed to create project: {response.status_code},{response.text}")

    def check_user_verified_in_xnat(self, login_id: str) -> dict:
        """
        Check if a user is verified in the XNAT system.

        :param login_id: The login ID of the user.
        :return: A dictionary with the verification status.
        """
        response = self._request('GET', f"/xapi/users/{login_id}/verified")
        if response.ok:
            return response.json()
        return None

    def verify_user_in_xnat(self, login_id: str) -> bool:
        """
        Verify a user in the XNAT system.

        :param login_id: The login ID of the user.
        :return: True if the user was successfully verified, False otherwise.
        """
        return self._request('PUT', f"/xapi/users/{login_id}/verified/true").status_code == 200

    def check_user_enabled_in_xnat(self, login_id: str) -> dict:
        """
        Check if a user is enabled in the XNAT system.

        :param login_id: The login ID of the user.
        :return: A dictionary with the enabled status.
        """
        response = self._request('GET', f"/xapi/users/{login_id}/enabled")
        if response.ok:
            return response.json()
        return None

    def enable_user_in_xnat(self, login_id: str) -> bool:
        """
        Enable a user in the XNAT system.

        :param login_id: The login ID of the user.
        :return: True if the user was successfully enabled, False otherwise.
        """
        return self._request('PUT', f"/xapi/users/{login_id}/enabled/true").status_code == 200

    def get_user_project_data(self, project_id: int) -> list:
        """
        Retrieve data for users in a specific XNAT project.

        :param project_id: The ID of the XNAT project.
        :return: A list of user data.
        """
        response = self._request('GET', f"/data/projects/{project_id}/users")
        if response.ok:
            result = response.json()
            return result.get("ResultSet", {}).get("Result", [])
        return []

    def add_user_to_project(self, login_id: str, email: str, project_id: int) -> bool:
        """
        Add a user to an XNAT project.

        :param login_id: The login ID of the user.
        :param email: The email of the user.
        :param project_id: The ID of the XNAT project.
        :return: True if the user was successfully added, False otherwise.
        """
        role = "member" if email and "student" not in email else "collaborator"
        return self._request('PUT', f"/data/projects/{project_id}/users/{role}/{login_id}/mail",
                             data={"email": email}).status_code == 200

    def close_connections(self):
        """
        Close any active connections to the XNAT system.
        """
        self._request('DELETE', "/xapi/users/active/m7666013")


class IntegrationManager:
    def __init__(self, canvas: CanvasIntegration, xnat: XNATIntegration):
        """
        Initialize the IntegrationManager with Canvas and XNAT instances.

        :param canvas: An instance of CanvasIntegration.
        :param xnat: An instance of XNATIntegration.
        """
        self.canvas = canvas
        self.xnat = xnat
        self.processed_count = 0
        self.verified_count = 0
        self.enabled_count = 0
        self.added_to_project_count = 0

    def create_xml(self, course_id, course_name):
        """
        Create an XML string for a new project.

        :param course_id: The ID of the Canvas course.
        :param course_name: The name of the Canvas course.
        :return: An XML string representing the project data.
        """
        logging.info(f"Creating new project for course {course_name}, with ID {course_id}")
        namespace = "http://nrg.wustl.edu/xnat"
        ET.register_namespace("xnat", namespace)

        # Create the root element with the namespace
        root = ET.Element("{http://nrg.wustl.edu/xnat}projectData")

        # Add sub-elements with the correct field names
        ET.SubElement(root, "{http://nrg.wustl.edu/xnat}ID").text = f"{course_id}"
        ET.SubElement(root, "{http://nrg.wustl.edu/xnat}secondary_ID").text = f"{course_id}"
        ET.SubElement(root, "{http://nrg.wustl.edu/xnat}name").text = f"{course_name}"

        xml_string = ET.tostring(root, encoding='utf-8', xml_declaration=True, method='xml').decode('utf-8')
        return (xml_string)

    def process_participant(self, participant, project_id, project_users):
        """
        Process a participant by verifying, enabling, and adding them to a project if necessary.

        :param participant: The participant data.
        :param project_id: The ID of the project.
        :param project_users: A list of current project users.
        """
        login_id = participant['login_id']
        email = participant['email']
        self.processed_count += 1
        if not login_id:
            logging.warning(
                f"Key 'login_id' not found in participant {participant['name']}, their status may be pending.")
            return

        if not self.xnat.check_user_verified_in_xnat(login_id):
            if self.xnat.verify_user_in_xnat(login_id):
                logging.info(f"The user {login_id} has been verified.")
                self.verified_count += 1

        if not self.xnat.check_user_enabled_in_xnat(login_id):
            if self.xnat.enable_user_in_xnat(login_id):
                logging.info(f"The user {login_id} has been enabled.")
                self.enabled_count += 1

        if login_id not in [user['login'] for user in project_users]:
            xnat_integration = self.xnat
            role = "member" if email and "student" not in email else "collaborator"
            if xnat_integration._request('PUT', f"/data/projects/{project_id}/users/{role}/{login_id}/mail",
                                         data={"email": email}).status_code == 200:
                logging.info(f"User {login_id} successfully added to project {project_id}.")
                self.added_to_project_count += 1
            else:
                logging.error(f"Failed to add user {login_id} to project {project_id}.")

    def execute_integration(self):
        """
        Execute the integration process between Canvas and XNAT.
        """
        self.xnat.get_user_token()
        course_ids, course_names = self.canvas.get_canvas_courses()
        project_ids = self.xnat.get_project_ids_list()
        xnat_users = self.xnat.get_users_in_xnat()
        print(f"Starting integration for {len(course_ids)} course(s) in Canvas...")
        logging.info(f"Started integration for {len(course_ids)} course(s) in Canvas...")
        print(f"Retrieving the XNAT user list from {self.xnat.xnat_url}, containing {len(xnat_users)} items...")
        logging.info(f"Retrieved the XNAT user list from {self.xnat.xnat_url}, containing {len(xnat_users)} items...")
        for course_id in course_ids:
            if f"{course_id}" not in project_ids:
                print(f"{course_id} not found in project_ids, creating project")
                course_name = course_names[course_ids.index(course_id)]
                xml_string = self.create_xml(course_id, course_name)
                self.xnat.create_project(xml_string)

        pbar_c = tqdm(course_ids, unit='courses')
        for course_id in pbar_c:
            pbar_c.set_description(f'Processing integration, course {course_id}')
            canvas_participants = self.canvas.get_canvas_participants(course_id)
            project_users = self.xnat.get_user_project_data(course_id)
            total_participants = len(canvas_participants)
            # Loop through every participant in the canvas_participants list
            pbar_p = tqdm(canvas_participants, unit='participants', leave=False)
            for participant in pbar_p:
                # Find the position of the participant in the canvas_participants list
                part_nr = pbar_p.n + 1
                pbar_p.set_description(f'Processing course {course_id}, user {part_nr}/{total_participants}')
                if 'login_id' in participant and participant['login_id'] in xnat_users:
                    self.process_participant(participant, course_id, project_users)
            # Log the counts at the end
        logging.info(f"Total users processed: {self.processed_count}")
        logging.info(f"Total users verified: {self.verified_count}")
        logging.info(f"Total users enabled: {self.enabled_count}")
        logging.info(f"Total users added to project: {self.added_to_project_count}")

        self.xnat.close_connections()

def setup(credentials: str):
    """
    Set up the integration by reading credentials from a YAML file.

    :param credentials: The path to the YAML file containing credentials.
    :return: Instances of CanvasIntegration and XNATIntegration.
    """
    with open(credentials) as cred_yaml:
        cred = yaml.safe_load(cred_yaml)
        canvas = CanvasIntegration(
            canvas_url=cred['canvas']['url'],
            canvas_token=cred['canvas']['token']
        )
        xnat = XNATIntegration(
            xnat_url=cred['xnat']['url'],
            username=cred['xnat']['username'],
            password=cred['xnat']['password']
        )
    logging.basicConfig(filename='logs/integration_log.txt', level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    return canvas, xnat

if __name__ == "__main__":
    canvas, xnat = setup('credentials.yaml')
    manager = IntegrationManager(canvas, xnat)
    manager.execute_integration()
