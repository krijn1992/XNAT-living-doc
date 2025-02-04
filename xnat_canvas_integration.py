########################################################################################################################
# Python script for integration between XNAT and Canvas
#
# Authors: Sjoerd Zagema, Krijn Tiek
#
# Version: 09012025
#
# Scope:
# This script provides an automated connection between the Medical Imaging Archive XNAT and Online Coursing Provider
# Canvas. The aim is to check the users for all courses that include imaging and whose images are stored on XNAT. By
# cross-referencing user lists between the applications we're able to enable accounts on XNAT of only those users who
# are a member of Canvas Courses linked to Medical Imaging. We're also able to automatically assign them to projects in
# XNAT that correspond to courses they follow in the Canvas application.
#
#
# To do:
# - Get all courses through functional account (now it is just a list)
# - Broaden information in logging
# - Create local cache with enabled accounts to skip next time
# - Other API optimisations
# - Unittests
#
########################################################################################################################
import requests
from tqdm import tqdm
import yaml
import logging


class CanvasIntegration:
    def __init__(self, canvas_url: str, canvas_token: str):
        # Initialize the CanvasIntegration class with the necessary URL, token, and project ID
        self.canvas_url = canvas_url
        self.canvas_token = canvas_token

    def _request(self, method: str, endpoint: str, params: dict = None) -> requests.Response:
        response = requests.request(method, f"{self.canvas_url}{endpoint}",
                                    headers={'Authorization': f'Bearer {self.canvas_token}'},
                                    params=params
                                    )
        if response.status_code not in [200, 204]:
            logging.error(f"API Error: {response.status_code} - {response.text}")
        return response

    def get_canvas_courses(self):
        # Should get all courses via functional account
        response = self._request('GET', "/courses",params={'enrollment_type': 'teacher'})
        course_ids = [course['id'] for course in response.json()]
        course_names = [course['name'] for course in response.json()]
        # Until this is an actual account, override the outcome
        # course_ids = [16583]
        return course_ids

    def get_canvas_participants(self, project_id: int) -> list:
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
        # Initialize the XNATIntegration class with the necessary credentials and project ID
        self.xnat_url = xnat_url
        self.username = username
        self.password = password
        self.token = ""

    def _init_request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> requests.Response:
        response = requests.request(method, f"{self.xnat_url}{endpoint}",
                                    auth=(self.username, self.password),
                                    json=data, params=params)
        if response.status_code not in [200, 204]:
            logging.error(f"API Error: {response.status_code} - {response.text}")
        return response

    def _request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> requests.Response:
        response = requests.request(method, f"{self.xnat_url}{endpoint}",
                                    headers={'Cookie': f'JSESSIONID={self.token}'},
                                    json=data, params=params)
        if response.status_code not in [200, 204]:
            logging.error(f"API Error: {response.status_code} - {response.text}")
        return response

    def get_user_token(self) -> str:
        response = self._init_request('POST', f"/data/JSESSION")
        if response.ok:
            self.token = response.cookies['JSESSIONID']
        return None

    def check_users_in_xnat(self) -> dict:
        response = self._request('GET', "/xapi/users")
        if response.ok:
            return response.json()
        return None

    def check_user_verified_in_xnat(self, login_id: str) -> dict:
        response = self._request('GET', f"/xapi/users/{login_id}/verified")
        if response.ok:
            return response.json()
        return None

    def verify_user_in_xnat(self, login_id: str) -> bool:
        return self._request('PUT', f"/xapi/users/{login_id}/verified/true").status_code == 200

    def check_user_enabled_in_xnat(self, login_id: str) -> dict:
        response = self._request('GET', f"/xapi/users/{login_id}/enabled")
        if response.ok:
            return response.json()
        return None

    def enable_user_in_xnat(self, login_id: str) -> bool:
        return self._request('PUT', f"/xapi/users/{login_id}/enabled/true").status_code == 200

    def get_user_project_data(self, project_id: int) -> list:
        response = self._request('GET', f"/data/projects/{project_id}/users")
        if response.ok:
            result = response.json()
            return result.get("ResultSet", {}).get("Result", [])
        return []

    def add_user_to_project(self, login_id: str, email: str, project_id: int) -> bool:
        role = "member" if email and "student" not in email else "collaborator"
        return self._request('PUT', f"/data/projects/{project_id}/users/{role}/{login_id}/mail",
                             data={"email": email}).status_code == 200

    def close_connections(self):
        self._request('DELETE', "/xapi/users/active/m7666013")


class IntegrationManager:
    def __init__(self, canvas: CanvasIntegration, xnat: XNATIntegration):
        # Initialize the IntegrationManager with canvas and xnat instances
        self.canvas = canvas
        self.xnat = xnat
        self.processed_count = 0
        self.verified_count = 0
        self.enabled_count = 0
        self.added_to_project_count = 0

    def process_participant(self, participant, project_id, project_users):
        # Extract login_id and email from the participant dictionary
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
            if self.xnat.add_user_to_project(login_id, email, project_id):
                logging.info(f"User {login_id} successfully added to project {project_id}.")
                self.added_to_project_count += 1
            else:
                logging.error(f"Failed to add user {login_id} to project {project_id}.")

    def execute_integration(self):
        self.xnat.get_user_token()
        projects = self.canvas.get_canvas_courses()
        total_projects = len(projects)
        xnat_logins = self.xnat.check_users_in_xnat()
        print(f"Starting integration for {total_projects} course(s) in Canvas...")
        logging.info(f"Starting integration for {total_projects} course(s) in Canvas...")
        print(f"Retrieving the XNAT user list from {self.xnat.xnat_url}, containing {len(xnat_logins)} items...")
        pbar_c = tqdm(projects, unit='courses')
        for project_id in pbar_c:
            pbar_c.set_description(f'Processing integration, course {project_id}')
            canvas_participants = self.canvas.get_canvas_participants(project_id)
            project_users = self.xnat.get_user_project_data(project_id)
            total_participants = len(canvas_participants)
            # Loop through every participant in the canvas_participants list
            pbar_p = tqdm(canvas_participants, unit='participants', leave=False)
            for participant in pbar_p:
                # Find the position of the participant in the canvas_participants list
                part_nr = pbar_p.n + 1
                pbar_p.set_description(f'Processing course {project_id}, user {part_nr}/{total_participants}')
                if 'login_id' in participant and participant['login_id'] in xnat_logins:
                    self.process_participant(participant, project_id, project_users)
            # Log the counts at the end
        logging.info(f"Total users processed: {self.processed_count}")
        logging.info(f"Total users verified: {self.verified_count}")
        logging.info(f"Total users enabled: {self.enabled_count}")
        logging.info(f"Total users added to project: {self.added_to_project_count}")

        self.xnat.close_connections()


def setup(credentials: str):
    # Open YAML file with credentials and link them to variables
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
    # Configure logging
    logging.basicConfig(filename='logs/integration_log.txt', level=logging.ERROR,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    return canvas, xnat


##########################################
canvas, xnat = setup('credentials.yaml')
manager = IntegrationManager(canvas, xnat)
manager.execute_integration()
##########################################
