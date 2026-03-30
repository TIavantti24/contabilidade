# STRATWs CIMAPRA — Sistema de Gestão de Indicadores

App web desenvolvido em Flask inspirado no STRATWs One, com os dados reais de indicadores da CIMAPRA.

---

## 🚀 Como rodar

### Opção 1 — Desenvolvimento local

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar variáveis (opcional)
cp .env.example .env
# edite o .env com SECRET_KEY e ADMIN_PASSWORD

# 3. Rodar
python app.py
```

Acesse: http://localhost:5000
Login padrão: `admin` / `Admin@2024!`

> **Coloque o arquivo Excel** em `/data/indicadores.xlsx` ou defina `EXCEL_PATH` no `.env`.

---

### Opção 2 — Docker (recomendado para produção)

```bash
# 1. Copiar .env
cp .env.example .env
# Edite com SECRET_KEY segura e ADMIN_PASSWORD forte

# 2. Criar pasta data e copiar o Excel
mkdir -p data
cp seu_arquivo.xlsx data/indicadores.xlsx

# 3. Subir
docker-compose up -d

# Ver logs
docker-compose logs -f
```

Acesse: http://localhost:5000

---

## 🔒 Segurança implementada

| Recurso | Detalhe |
|---|---|
| Senhas | Hash bcrypt via Werkzeug |
| Sessão | Cookie HttpOnly + SameSite=Lax |
| Sessão em prod | Cookie Secure (HTTPS) |
| Autenticação | Decorator `@login_required` em todas as rotas |
| Admin | Decorator `@admin_required` separado |
| Erros | Handlers 403/404 customizados |
| WSGI prod | Gunicorn (4 workers) — nunca Flask dev server |
| Container | Usuário não-root (UID 1000) |
| Excel | Montado read-only no Docker |
| Segredos | Via variáveis de ambiente, nunca hardcoded |

---

## 🌐 Deploy em VPS / Cloud

Para produção com HTTPS, coloque o Nginx na frente:

```nginx
server {
    listen 443 ssl;
    server_name seu.dominio.com;

    ssl_certificate     /etc/ssl/certs/seu_cert.pem;
    ssl_certificate_key /etc/ssl/private/sua_chave.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

---

## 📁 Estrutura do projeto

```
stratws_app/
├── app.py                  # Aplicação principal
├── requirements.txt        # Dependências Python
├── Dockerfile              # Imagem Docker segura (multi-stage)
├── docker-compose.yml      # Orquestração
├── .env.example            # Variáveis de ambiente (copie para .env)
├── .gitignore
├── instance/               # Banco SQLite (gerado automaticamente)
└── templates/
    ├── base.html           # Layout com sidebar
    ├── login.html          # Tela de login
    ├── dashboard.html      # Dashboard com gráficos
    ├── indicadores.html    # Lista com filtros e paginação
    ├── detalhe.html        # Detalhe + gráfico evolução
    ├── admin_users.html    # Gestão de usuários
    └── error.html          # Páginas de erro 403/404
```

---

## ✏️ Personalização

- **Trocar logo/nome**: edite `templates/base.html` (`.sidebar-logo`)
- **Adicionar usuários**: acesse `/admin/users` com a conta admin
- **Banco PostgreSQL**: defina `DATABASE_URL=postgresql://user:pass@host/db` no `.env`
- **Novo Excel**: defina `EXCEL_PATH` e reinicie (os dados são importados automaticamente se o banco estiver vazio)
