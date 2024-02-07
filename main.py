from fastapi import FastAPI, Depends, HTTPException, status
import os
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from typing import Optional
from xmlrpc.client import ServerProxy
import datetime
import base64
from xmlrpc.client import ServerProxy, Error as XmlRpcError
from PyPDF2 import PdfReader

# Keys de JWT
SECRET_KEY = "WCTi4FvUmr891sNzASFDwi85Ri7gR8a0DSF9d2l59UbDKEMts"
ALGORITHM = "HS256"

# Keys de Odoo
url = 'https://integra12.odoo.com/'
db = 'integra12'
username = 'soporte@empresasintegra.cl'
password = 'MN2o24*'

app = FastAPI()

# Clases
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# verificar el token
def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    return token_data

# Endpoint para obtener el token
@app.post("/token")
async def login_for_access_token(form_data: TokenData):
    # Aquí podrías añadir tu lógica para verificar la identidad del usuario
    if form_data.username != 'hola':
        return {"error": "Usuario o contraseña incorrectos"}
    # access_token_expires = datetime.timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": form_data.username}#, expires_delta=access_token_expires
    )
    print(access_token)
    #return {"access_token": access_token, "token_type": "bearer"}
    return "Token generado"

# Crear un token de acceso
def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Dependencia para obtener el usuario actual
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return verify_token(token, credentials_exception)

# Endpoint protegido que requiere autenticación
@app.get("/users/me")
async def read_users_me(current_user: TokenData = Depends(get_current_user)):
    return current_user

    

@app.post("/conexion")
def test_odoo(data: dict):
    print(data)
    try:
        # Authentication in Odoo
        common = ServerProxy('{}/xmlrpc/2/common'.format(url))
        uid = common.authenticate(db, username, password, {})

        if uid:
            models = ServerProxy('{}/xmlrpc/2/object'.format(url))
            roles = models.execute_kw(db, uid, password, 'sign.item.role', 'search_read', [[]], {'fields': ['id', 'name']})
            role_mapping = {role['name']: role['id'] for role in roles}

            # Assuming 'Customer' and 'Employee' are the names of roles in your Odoo instance
            customer_role_id = role_mapping.get('Customer')
            employee_role_id = role_mapping.get('Employee')

            # Obtener los SigningParties de los datos recibidos
            signing_parties = data.get('SigningParties')

            #obtener documento
            documento = data.get('document')

            # cantidad de paginas del documento
            num_pages = data.get('numberPages')

            # Obtener los nombres y direcciones de los SigningParties
            for signing_party in signing_parties:
                name = signing_party.get('name')
                address = signing_party.get('address')
                role = signing_party.get('legalName')
                partner_data= {'name': name, 'email': address}
                partner_id = models.execute_kw(db, uid, password, 'res.partner', 'search', [[('email', '=', partner_data['email'])]])
                if not partner_id:
                    partner_id = models.execute_kw(db, uid, password, 'res.partner', 'create', [partner_data])
                else:
                    partner_id = partner_id[0]
                if role == 'Trabajador':
                    signature_field_customer = {'type_id':1,'required':True,'name': partner_data['name'], 'page': num_pages, 'responsible_id': customer_role_id,'posX':0.15,'posY':0.85,'width':0.2,'height':0.1,'required':True}
                    partner_id_1 = partner_id
                else:
                    signature_field_employee = {'type_id':2,'required':True,'name': partner_data['name'], 'page': num_pages,'responsible_id': employee_role_id,'posX':0.7,'posY':0.85,'width':0.2,'height':0.1,'required':True}
                    partner_id_2 = partner_id


            attachment = {'name': 'prueba.pdf', 'datas': documento, 'type': 'binary'}
            attachment_id = models.execute_kw(db, uid, password, 'ir.attachment', 'create', [attachment])

            # Create template
            template_data = {'name': 'Template prueba', 
                             'attachment_id': attachment_id,
                             'sign_item_ids': [
                (0, 0, signature_field_customer),
                (0, 0, signature_field_employee)
            ]}
            template_id = models.execute_kw(db, uid, password, 'sign.template', 'create', [template_data])

            print(template_id)
            # Create signature request
            request_data = {
                'template_id': template_id,
                'subject': 'Solicitud de firma',
                'reference': 'Solicitud de firma',
                'request_item_ids': [
                    (0, 0, {'partner_id': partner_id_1, 'role_id': customer_role_id}), 
                    (0, 0, {'partner_id': partner_id_2, 'role_id': employee_role_id}),
                ]
            }
            request_id = models.execute_kw(db, uid, password, 'sign.request', 'create', [request_data])
            print(request_id)

            return {"success": "Solicitud de firma enviada correctamente."}
        else:
            return {"error": "Autenticación fallida. Verifica tus credenciales."}
    except ConnectionError:
        return {"error": "Error de conexión a Odoo. Verifica la URL."}
    except XmlRpcError as xe:
        return {"error": f"Error en la llamada XML-RPC a Odoo: {xe}"}
    except ValueError as ve:
        return {"error": f"Error de valor: {ve}"}
    except Exception as e:
        return {"error": f"Error desconocido: {str(e)}"}
