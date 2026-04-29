from langchain_core.tools import tool

def create_static_context_tools():

    @tool
    def get_markdown_context() -> str:
        """
        Get the metadata schema in markdown format.
        This is providing a description how you can query the dataset.
        """
        with open("data/database_schema.md", "r") as schema:
            schema_markdown = schema.read()
        return schema_markdown
    
    @tool
    def get_yaml_context() -> str:
        """
        Get the metadata schema in yaml format.
        This is providing a description how you can query the dataset.
        """
        with open("data/database_schema.yaml", "r") as schema:
            schema_yaml = schema.read()
        return schema_yaml
        
    return [get_markdown_context, get_yaml_context]