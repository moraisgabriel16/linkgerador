from flask import Flask, render_template, request, redirect, url_for, flash, session, current_app
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from io import BytesIO
from PIL import Image
import cloudinary
import cloudinary.uploader
import cloudinary.api
import re
from bson.objectid import ObjectId
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer import OAuth2ConsumerBlueprint

app = Flask(__name__)
# --- Configuração do Cloudinary ---
cloudinary.config(
    cloud_name = 'djqeq4f2l',
    api_key = '914332463917138',
    api_secret = 'gYvTTXlzjjO_8rxd9oB627674tc',
    secure = True
)
# MUDE ISSO PARA UMA CHAVE FORTE E ÚNICA EM PRODUÇÃO!
# Gere uma string aleatória longa para produção. Ex: os.urandom(24).hex()
app.secret_key = 'sua_chave_secreta_aqui_para_sessoes_muito_segura_e_longa_para_producao'

# --- Configuração do MongoDB Atlas ---
# IMPORTANTE: Em ambiente de produção, use variáveis de ambiente!
# Exemplo: MONGO_URI = os.environ.get("MONGO_URI")

MONGO_URI_ATLAS = "mongodb+srv://odonto1:gaga123@cluster0.rx2q20y.mongodb.net/link_in_bio_db?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(MONGO_URI_ATLAS)
db = client.link_in_bio_db

# Coleções do MongoDB
users_collection = db.users
profiles_collection = db.profiles

# --- Configuração de Upload de Imagens ---
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Novo limite de upload: 4MB
MAX_IMAGE_SIZE_MB = 4
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_IMAGE_SIZE_MB * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Funções Auxiliares de Lógica ---
def generate_unique_slug(name, user_id, current_slug=None):
    """Gera um slug URL-friendly, garantindo que seja único para o usuário ou em geral."""
    base_slug = re.sub(r'[^a-z0-9\s-]', '', name.lower())
    base_slug = re.sub(r'\s+', '-', base_slug)
    base_slug = re.sub(r'-+', '-', base_slug).strip('-')

    if not base_slug:
        base_slug = "perfil"

    if current_slug == base_slug:
        return base_slug

    counter = 0
    slug = base_slug
    while True:
        existing_profile = profiles_collection.find_one({
            'slug_url': slug,
            'user_id': {'$ne': ObjectId(user_id)}
        })
        if not existing_profile:
            break
        counter += 1
        slug = f"{base_slug}-{counter}"
    return slug

def process_whatsapp_link(number):
    """Converte um número de telefone (DDD+Número) para a URL do WhatsApp."""
    if number:
        # Remove caracteres não numéricos
        clean_number = re.sub(r'[^0-9]', '', number)
        if clean_number:
            # Assumimos Brasil (55). Se o número já começar com 55, não adiciona de novo.
            if not clean_number.startswith('55'):
                clean_number = '55' + clean_number
            return f"https://wa.me/{clean_number}"
    return ""

def extract_whatsapp_number(url):
    """Extrai o número de telefone de uma URL do WhatsApp."""
    if url and ("wa.me/" in url or "api.whatsapp.com/send" in url):
        match = re.search(r'(\d+)', url)
        if match:
            number = match.group(1)
            # Remove o prefixo 55 se estiver presente
            if number.startswith('55'):
                return number[2:]
            return number
    return ""

def process_instagram_link(username):
    """Converte um nome de usuário do Instagram para a URL completa."""
    if username:
        clean_username = username.strip().replace('@', '') # Remove espaços e @
        if clean_username:
            return f"https://www.instagram.com/{clean_username}"
    return ""

def extract_instagram_username(url):
    """Extrai o nome de usuário do Instagram de uma URL completa."""
    if url and "instagram.com/" in url:
        parts = url.split('/')
        if len(parts) > 3 and parts[2] == "www.instagram.com":
            username = parts[3].split('?')[0].split('#')[0] # Remove query params e hash
            return username.strip()
    return ""

# --- Rotas da Aplicação ---

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form.get('confirm_password')

        if not full_name or not username or not email or not password or not confirm_password:
            flash('Por favor, preencha todos os campos.', 'danger')
            return redirect(url_for('register'))

        if len(password) < 8:
            flash('A senha deve ter pelo menos 8 caracteres.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return redirect(url_for('register'))

        if users_collection.find_one({'email': email}):
            flash('Este e-mail já está cadastrado. Tente fazer login.', 'warning')
            return redirect(url_for('register'))

        if users_collection.find_one({'username': username}):
            flash('Este nome de usuário já está em uso. Escolha outro.', 'warning')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        new_user = {
            'full_name': full_name,
            'username': username,
            'email': email,
            'password': hashed_password
        }
        users_collection.insert_one(new_user)
        flash('Cadastro realizado com sucesso! Faça login para continuar.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = users_collection.find_one({'email': email})

        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            flash('Login bem-sucedido!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('E-mail ou senha incorretos.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('full_name', None)
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Você precisa estar logado para acessar esta página.', 'danger')
        return redirect(url_for('login'))

    user_id = session['user_id']
    username = session['username']
    full_name = session.get('full_name', username)

    user_profile = profiles_collection.find_one({'user_id': ObjectId(user_id)})

    return render_template('dashboard.html', username=username, full_name=full_name, user_profile=user_profile)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        flash('Você precisa estar logado para acessar esta página.', 'danger')
        return redirect(url_for('login'))

    user_id = session['user_id']
    user_profile = profiles_collection.find_one({'user_id': ObjectId(user_id)})

    # Variáveis para preencher o formulário (no GET ou em caso de erro no POST)
    whatsapp_number = ""
    instagram_username = ""
    # Se há um perfil existente, extrai os dados simplificados dos links
    if user_profile:
        whatsapp_number = extract_whatsapp_number(user_profile.get('link_whatsapp'))
        instagram_username = extract_instagram_username(user_profile.get('link_instagram'))
    # Se o request for POST e houve um erro, preenche com os dados que o usuário tentou enviar
    elif request.method == 'POST' and request.form:
        whatsapp_number = request.form.get('link_whatsapp')
        instagram_username = request.form.get('link_instagram')


    if request.method == 'POST':
        nome_vendedor = request.form.get('nome_vendedor')
        empresa_nome = request.form.get('empresa_nome')
        cargo = request.form.get('cargo')
        descricao = request.form.get('descricao')
        whatsapp_input = request.form.get('link_whatsapp')
        instagram_input = request.form.get('link_instagram')

        # Converte os inputs simplificados para as URLs completas
        link_whatsapp_full = process_whatsapp_link(whatsapp_input)
        link_instagram_full = process_instagram_link(instagram_input)

        link_catalogo = request.form.get('link_catalogo')
        link_website = request.form.get('link_website')
        background_color = request.form.get('background_color', 'linear-gradient(135deg, #F0F2F5, #FFFFFF)')
        custom_background_css = request.form.get('custom_background_css') # NOVO: Captura string CSS
        custom_slug = request.form.get('custom_slug')

        # Validação básica dos campos obrigatórios
        if not nome_vendedor or not cargo or not descricao:
            flash('Nome, Cargo e Descrição são campos obrigatórios.', 'danger')
            # Passa a configuração e os dados brutos de volta para o template em caso de erro
            return render_template('edit_profile.html', profile=user_profile, form_data=request.form,
                                   max_upload_size_mb=current_app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024),
                                   whatsapp_number=whatsapp_input,
                                   instagram_username=instagram_input)



        # Remoção de foto de perfil
        profile_pic_filename = None
        if request.form.get('profile_pic_filename', '').strip() == '':
            # Remove do Cloudinary
            try:
                cloudinary.uploader.destroy(f"profile_pic_{user_id}")
            except Exception:
                pass
        else:
            profile_pic_file = request.files.get('profile_pic_file')
            if profile_pic_file and allowed_file(profile_pic_file.filename):
                # Compressão da imagem antes do upload
                try:
                    img = Image.open(profile_pic_file)
                    # Corrige orientação EXIF se necessário
                    if hasattr(Image, 'exif_transpose'):
                        img = Image.exif_transpose(img)
                    else:
                        try:
                            exif = img._getexif()
                            if exif:
                                orientation = exif.get(274)
                                if orientation == 3:
                                    img = img.rotate(180, expand=True)
                                elif orientation == 6:
                                    img = img.rotate(270, expand=True)
                                elif orientation == 8:
                                    img = img.rotate(90, expand=True)
                        except Exception:
                            pass
                    img_format = img.format if img.format else 'JPEG'
                    max_size = (800, 800)
                    img.thumbnail(max_size, Image.LANCZOS)
                    buffer = BytesIO()
                    img.save(buffer, format=img_format, quality=80, optimize=True)
                    buffer.seek(0)
                    result = cloudinary.uploader.upload(buffer,
                        folder='profile_pics',
                        public_id=f"profile_pic_{user_id}",
                        overwrite=True,
                        resource_type="image"
                    )
                    profile_pic_filename = result['secure_url']
                except Exception:
                    profile_pic_file.seek(0)
                    result = cloudinary.uploader.upload(profile_pic_file,
                        folder='profile_pics',
                        public_id=f"profile_pic_{user_id}",
                        overwrite=True,
                        resource_type="image"
                    )
                    profile_pic_filename = result['secure_url']
            else:
                profile_pic_filename = request.form.get('profile_pic_filename') or (user_profile.get('profile_pic_filename') if user_profile else None)

        # Remoção de logo
        logo_filename = None
        if request.form.get('logo_filename', '').strip() == '':
            try:
                cloudinary.uploader.destroy(f"logo_{user_id}")
            except Exception:
                pass
        else:
            logo_file = request.files.get('logo_file')
            if logo_file and allowed_file(logo_file.filename):
                # Compressão da imagem antes do upload
                try:
                    img = Image.open(logo_file)
                    # Corrige orientação EXIF se necessário
                    if hasattr(Image, 'exif_transpose'):
                        img = Image.exif_transpose(img)
                    else:
                        try:
                            exif = img._getexif()
                            if exif:
                                orientation = exif.get(274)
                                if orientation == 3:
                                    img = img.rotate(180, expand=True)
                                elif orientation == 6:
                                    img = img.rotate(270, expand=True)
                                elif orientation == 8:
                                    img = img.rotate(90, expand=True)
                        except Exception:
                            pass
                    img_format = img.format if img.format else 'PNG'
                    max_size = (800, 800)
                    img.thumbnail(max_size, Image.LANCZOS)
                    buffer = BytesIO()
                    img.save(buffer, format=img_format, quality=80, optimize=True)
                    buffer.seek(0)
                    result = cloudinary.uploader.upload(buffer,
                        folder='logos',
                        public_id=f"logo_{user_id}",
                        overwrite=True,
                        resource_type="image"
                    )
                    logo_filename = result['secure_url']
                except Exception:
                    logo_file.seek(0)
                    result = cloudinary.uploader.upload(logo_file,
                        folder='logos',
                        public_id=f"logo_{user_id}",
                        overwrite=True,
                        resource_type="image"
                    )
                    logo_filename = result['secure_url']
            else:
                logo_filename = request.form.get('logo_filename') or (user_profile.get('logo_filename') if user_profile else None)

        # Geração do slug
        slug_source = custom_slug if custom_slug else nome_vendedor
        generated_slug = generate_unique_slug(slug_source, user_id, user_profile.get('slug_url') if user_profile else None)

        # Processa campos dinâmicos de outros links
        other_links = []
        processed_idxs = set()
        for key in request.form:
            if key.startswith('other_link_name_'):
                idx = key.split('other_link_name_')[1]
                if idx in processed_idxs:
                    continue
                processed_idxs.add(idx)
                name = request.form.get(f'other_link_name_{idx}', '').strip()
                url = request.form.get(f'other_link_url_{idx}', '').strip()
                # Salva se pelo menos um dos campos estiver preenchido
                if name or url:
                    other_links.append({'name': name, 'url': url})

        # Preparar os dados para salvar/atualizar no MongoDB
        profile_data = {
            'user_id': ObjectId(user_id),
            'nome_vendedor': nome_vendedor,
            'empresa_nome': empresa_nome,
            'cargo': cargo,
            'descricao': descricao,
            'link_whatsapp': link_whatsapp_full, # Salva a URL COMPLETA
            'link_catalogo': link_catalogo,
            'link_website': link_website,
            'link_instagram': link_instagram_full, # Salva a URL COMPLETA
            'profile_pic_filename': profile_pic_filename,
            'logo_filename': logo_filename,
            'slug_url': generated_slug,
            'background_color': background_color,
            'custom_background_css': custom_background_css, # Salva a string CSS do fundo
            'other_links': other_links
        }

        if user_profile:
            profiles_collection.update_one(
                {'_id': user_profile['_id']},
                {'$set': profile_data}
            )
            flash('Perfil atualizado com sucesso!', 'success')
        else:
            profiles_collection.insert_one(profile_data)
            flash('Perfil criado com sucesso!', 'success')

        return redirect(url_for('dashboard'))

    # Se GET request, renderiza o formulário com dados existentes (se houver)
    # E passa todas as variáveis necessárias para o template
    return render_template('edit_profile.html', profile=user_profile,
                           max_upload_size_mb=current_app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024),
                           whatsapp_number=whatsapp_number,
                           instagram_username=instagram_username)


# Configuração do Google OAuth

# Configuração do Google OAuth (ajuste callback e variáveis de ambiente)
google_bp = make_google_blueprint(
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    scope=["openid", "email", "profile"],
    redirect_url="/google"  # Redireciona para /google após login
)
app.register_blueprint(google_bp, url_prefix="/google_login")



@app.route("/google")
def google_login():
    if not google.authorized:
        return redirect(url_for("google.login"))
    resp = google.get("userinfo")
    assert resp.ok, resp.text
    info = resp.json()
    email = info.get("email")
    full_name = info.get("name", email.split("@")[0])
    username = info.get("given_name", email.split("@")[0])
    user = users_collection.find_one({"email": email})
    if not user:
        new_user = {
            "full_name": full_name,
            "username": username,
            "email": email,
            "password": ""  # Usuário Google não tem senha local
        }
        users_collection.insert_one(new_user)
        user = users_collection.find_one({"email": email})
        flash("Cadastro realizado com sucesso!", "success")
    else:
        flash("Login bem-sucedido!", "success")
    session["user_id"] = str(user["_id"])
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]
    return redirect(url_for("dashboard"))


if __name__ == '__main__':
    # Garante que a pasta de uploads existe ao iniciar o app
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)

# Mover a rota dinâmica para o final do arquivo
@app.route('/<string:slug>')
def public_profile(slug):
    ROUTES_FIXAS = {'login', 'register', 'dashboard', 'edit_profile', 'logout', 'static', 'favicon.ico'}
    if slug in ROUTES_FIXAS:
        return redirect(url_for(slug))

    profile = profiles_collection.find_one({'slug_url': slug})
    if not profile:
        flash('Perfil não encontrado.', 'danger')
        return redirect(url_for('home'))

    # Decide qual background usar: customizado se existir, senão cor sólida, senão padrão
    chosen_background = profile.get('custom_background_css')
    if not chosen_background:
        chosen_background = profile.get('background_color', 'linear-gradient(135deg, #F0F2F5, #FFFFFF)')

    return render_template('public_page.html', profile=profile, chosen_background=chosen_background)
