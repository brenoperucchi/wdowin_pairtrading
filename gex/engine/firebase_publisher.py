import os
import datetime
import firebase_admin
from firebase_admin import credentials, db

def push_walls_to_firebase(walls, database_url="https://wdo-win-dashboard-default-rtdb.firebaseio.com"):
    """
    Publica o array de walls no Firebase RTDB no no /daily_levels/win_gex.
    """
    if not firebase_admin._apps:
        # serviceAccountKey.json fica na raiz do projeto (dois niveis acima de engine/)
        gex_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(gex_dir)
        cred_path = os.path.join(project_root, "serviceAccountKey.json")
        
        if not os.path.exists(cred_path):
            print(f"Erro: serviceAccountKey.json nao encontrado em {cred_path}")
            return False
            
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': database_url
        })
        
    ref = db.reference('daily_levels/win_gex')
    
    payload = {
        "last_update": datetime.datetime.utcnow().isoformat() + "Z",
        "walls": walls
    }
    
    ref.set(payload)
    print(f"[{payload['last_update']}] GEX Walls publicadas no Firebase. ({len(walls)} linhas)")
    return True
