from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
user_id = ""

supabase: Client = create_client(url, key)

def sign_out():
    """Cerrar sesión en Supabase."""
    response = supabase.auth.sign_out()
    return response
    