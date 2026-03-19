import requests as r
import os
from dotenv import load_dotenv

class manageInstance():
    def __init__(self):
        load_dotenv(override=True)
        self.BASE_URL = "https://api.neo4j.io"
        AUTH = (os.getenv("CLIENT_ID"), os.getenv("CLIENT_SECRET"))
        data = {'grant_type': 'client_credentials',}
        response = r.post(f"{self.BASE_URL}/oauth/token", data=data, auth=AUTH)
        if response.status_code == 200:
            self.token = response.json().get('access_token')
            self.duration = response.json().get('expires_in')
        else:
            raise Exception(f"ERROR: {response.status_code}")

    def getInstances(self):
        headers = {
            "accept": "application/json",
            "Authorization": "Bearer " + self.token
        }
        response = r.get(f"{self.BASE_URL}/v1/instances", headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"ERROR: {response.status_code}. Message: {response.text}")

    def createInstance(self, project_id, instance_name, instance_size):
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.token
        }
        config = {
            "version": "5",
            "region": "europe-west1",
            "memory": f"{instance_size}GB",
            "name": instance_name,
            "tenant_id": project_id,
            "type": "professional-db",
            "cloud_provider": "gcp"
        }

        response = r.post(f"{self.BASE_URL}/v1/instances", headers=headers, json=config)
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception(f"ERROR: {response.status_code}. Message: {response.text}")

    def getStatus(self, instance_id):
        headers = {
            "accept": "application/json",
            "Authorization": "Bearer " + self.token
        }
        response = r.get(f"{self.BASE_URL}/v1/instances/{instance_id}", headers=headers)
        if response.status_code == 200:
            return response.json()["data"]["status"]
        else:
            raise Exception(f"ERROR: {response.status_code}. Message: {response.text}")

    def pause(self, instance_id):
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.token
        }
        response = r.post(f"{self.BASE_URL}/v1/instances/{instance_id}/pause", headers=headers)
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception(f"ERROR: {response.status_code}. Message: {response.text}")

    def resume(self, instance_id):
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.token
        }
        response = r.post(f"{self.BASE_URL}/v1/instances/{instance_id}/resume", headers=headers)
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception(f"ERROR: {response.status_code}. Message: {response.text}")

    def setSize(self, instance_id, memory, storage):
        #Check Ratio
        if memory / storage not in [1/2, 1/4, 1/8, 1/16]:
            raise Exception("Memory to storage ratio must be 1:2, 1:4, 1:8, or 1:16")

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.token
        }
        config = {"memory": f"{memory}GB", "storage": f"{storage}GB"}

        response = r.patch(f"{self.BASE_URL}/v1/instances/{instance_id}", headers=headers, json=config)
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception(f"ERROR: {response.status_code}. Message: {response.text}")

    def deleteInstance(self, instance_id):
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.token
        }
        response = r.delete(f"{self.BASE_URL}/v1/instances/{instance_id}", headers=headers)
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception(f"ERROR: {response.status_code}. Message: {response.text}")