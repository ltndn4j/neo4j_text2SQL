import neo4jHelpers.auraAPI as aura
import neo4j
import time
import os

def getDriver() -> neo4j.GraphDatabase.driver:
    if (os.getenv("NEO4J_URI") is not None):
        return neo4j.GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")))
    project_id = os.getenv("PROJECT_ID")
    instance_name = os.getenv("NEO4J_INSTANCE_NAME")
    
    manageInstance = aura.manageInstance()
    print(f"Token expires in {manageInstance.duration} seconds")
    start = time.time()

    instances = manageInstance.getInstances()
    #check if instance exists
    for instance in instances['data']:
        if instance['name'] == instance_name:
            print(f"Instance {instance_name} already exists with id {instance['id']}")
            instance_id = instance['id']
            pwd = os.getenv("NEO4J_PASSWORD")
            if "paused" == manageInstance.getStatus(instance_id):
                manageInstance.resume(instance_id)
            break
    else:
        print(f"Instance {instance_name} not found, creating...")
        response = manageInstance.createInstance(project_id, instance_name, 2)
        instance_id = response['data']['id']
        pwd = response['data']['password']
        print(f"\033[91mDON'T FORGET TO UPDATE THE PASSWORD IN THE .env FILE: \033[0m{pwd}")

    while "running" != manageInstance.getStatus(instance_id):
        print(f"Waiting for instance to run...Please wait...[{round(time.time() - start)}s]")
        time.sleep(60)
    return neo4j.GraphDatabase.driver(f"neo4j+s://{instance_id}.databases.neo4j.io", auth=("neo4j", pwd))

def destroyInstance(instance_id):
    manageInstance = aura.manageInstance()
    manageInstance.deleteInstance(instance_id)