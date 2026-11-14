import io
import boto3
from flask import Flask, request, redirect, url_for, send_file, render_template_string

app = Flask(__name__)
BUCKET_NAME = "galeria-imagens"

# Conexão com o S3 do LocalStack
s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:4566",
    aws_access_key_id="test",
    aws_secret_access_key="test",
    region_name="us-east-1"
)

HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Galeria S3 - LocalStack</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #f4f6f8; color: #333; }
        .card { background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.08); margin-bottom: 24px; }
        h1, h2 { margin-top: 0; }
        button, .btn { background: #0066cc; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; text-decoration: none; cursor: pointer; display: inline-block; }
        button:hover, .btn:hover { background: #0052a3; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #ddd; vertical-align: middle; }
        img.preview { width: 60px; height: 60px; object-fit: cover; border-radius: 4px; border: 1px solid #ccc; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Upload de Imagens (Amazon S3 LocalStack)</h1>
        <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="arquivo" accept="image/*" required>
            <button type="submit">Enviar para o S3</button>
        </form>
    </div>

    <div class="card">
        <h2>Arquivos no Bucket: {{ bucket }}</h2>
        {% if arquivos %}
        <table>
            <thead>
                <tr>
                    <th>Prévia</th>
                    <th>Nome do Arquivo</th>
                    <th>Tamanho</th>
                    <th>Ação</th>
                </tr>
            </thead>
            <tbody>
                {% for arq in arquivos %}
                <tr>
                    <td><img class="preview" src="/view/{{ arq.Key }}" alt="preview"></td>
                    <td>{{ arq.Key }}</td>
                    <td>{{ (arq.Size / 1024)|round(1) }} KB</td>
                    <td><a class="btn" href="/download/{{ arq.Key }}">Download</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p>Nenhuma imagem encontrada no bucket.</p>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    response = s3.list_objects_v2(Bucket=BUCKET_NAME)
    arquivos = response.get("Contents", [])
    return render_template_string(HTML_PAGE, arquivos=arquivos, bucket=BUCKET_NAME)

@app.route("/upload", methods=["POST"])
def upload():
    arquivo = request.files.get("arquivo")
    if arquivo and arquivo.filename:
        s3.upload_fileobj(arquivo, BUCKET_NAME, arquivo.filename)
    return redirect(url_for("index"))

@app.route("/view/<path:filename>")
def view_file(filename):
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=filename)
    return send_file(io.BytesIO(obj["Body"].read()), download_name=filename, as_attachment=False)

@app.route("/download/<path:filename>")
def download_file(filename):
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=filename)
    return send_file(io.BytesIO(obj["Body"].read()), download_name=filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
