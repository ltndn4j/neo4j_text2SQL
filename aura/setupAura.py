import aura.manageInstance as mi
import time

def getInstanceId(project_id,instance_name):
    manageInstance = mi.manageInstance()
    print(f"Token expires in {manageInstance.duration} seconds")
    start = time.time()

    instances = manageInstance.getInstances()
    #check if instance exists
    for instance in instances['data']:
        if instance['name'] == instance_name:
            print(f"Instance {instance_name} already exists with id {instance['id']}")
            instance_id = instance['id']
            pwd = None
            if "paused" == manageInstance.getStatus(instance_id):
                manageInstance.resume(instance_id)
            break
    else:
        print(f"Instance {instance_name} not found, creating...")
        response = manageInstance.createInstance(project_id, instance_name, 2)
        instance_id = response['data']['id']
        pwd = response['data']['password']
        print(f"\033[91mDON'T FORGET TO UPDATE THE PASSWORD IN THE .ENV FILE: \033[0m{pwd}")

    while "running" != manageInstance.getStatus(instance_id):
        print(f"Waiting for instance to run...Please wait...[{round(time.time() - start)}s]")
        time.sleep(60)
    return {
        "neo4j_uri": f"neo4j+s://{instance_id}.databases.neo4j.io",
        "neo4j_username": "neo4j",
        "neo4j_password": pwd
    }

def destroyInstance(instance_id):
    manageInstance = mi.manageInstance()
    manageInstance.deleteInstance(instance_id)

if __name__ == "__main__":
    instance_name = "text2sql-instance"
    project_id = "875a99c2-d2e2-4bf6-8ddb-78dcc7d2fecc"
    print(getInstanceId(project_id, instance_name))
