from ragin import ServerlessApp, Field, Model, resource


@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str
    role: str = "member"


app = ServerlessApp()
