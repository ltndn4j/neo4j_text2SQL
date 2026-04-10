# tools.py
from langchain_core.tools import tool

def create_dummy_tools():

    @tool
    def purpose(text: str) -> str:
        """
        Greets a person or thing by returning a formatted hello message and the purpose of the agent.
        Use this whenever you need to say hello or process a greeting string.
        """
        return f"Hello, {text}! Welcome to this agent which is used to answer questions about the dataset on employees."
    
    return [purpose]