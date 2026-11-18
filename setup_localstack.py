import io
import os
import sys
import time
import zipfile
import boto3
from botocore.exceptions import ClientError

ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
BUCKET_ORIGEM = "galeria-imagens"
BUCKET_PROCESSADAS = "galeria-processadas"
TABELA_USUARIOS = "Usuarios"
LAMBDA_NAME = "processar-imagem-s3"
LAMBDA_ROLE = "arn:aws:iam::000000000000:role/lambda-s3-role"


def get_client(service_name: str):
    return boto3.client(
        service_name,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name=REGION,
    )


def configurar_s3():
    """Cria os buckets S3 de origem (Atividade #1) e de destino (Atividade #3)."""
    s3 = get_client("s3")
    existentes = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]

    for bucket in (BUCKET_ORIGEM, BUCKET_PROCESSADAS):
        if bucket not in existentes:
            s3.create_bucket(Bucket=bucket)
            print(f"[S3] Bucket '{bucket}' criado com sucesso.")
        else:
            print(f"[S3] Bucket '{bucket}' já existe.")


def configurar_dynamodb():
    """Cria a tabela 'Usuarios' no DynamoDB para cadastro e autenticação (Atividade #2)."""
    dynamodb = get_client("dynamodb")
    tabelas = dynamodb.list_tables().get("TableNames", [])

    if TABELA_USUARIOS not in tabelas:
        dynamodb.create_table(
            TableName=TABELA_USUARIOS,
            KeySchema=[
                {"AttributeName": "username", "KeyType": "HASH"},  # Partition Key
            ],
            AttributeDefinitions=[
                {"AttributeName": "username", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        waiter = dynamodb.get_waiter("table_exists")
        waiter.wait(TableName=TABELA_USUARIOS)
        print(f"[DynamoDB] Tabela '{TABELA_USUARIOS}' criada com sucesso.")
    else:
        print(f"[DynamoDB] Tabela '{TABELA_USUARIOS}' já existe.")


def empacotar_lambda() -> bytes:
    """
    Cria o pacote ZIP em memória (e salva em disco como lambda_function.zip)
    contendo lambda_function.py e a biblioteca Pillow (PIL) caso disponível no venv,
    garantindo que a função Lambda consiga processar imagens reais no container Python 3.12.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    lambda_file = os.path.join(base_dir, "lambda_function.py")
    zip_path = os.path.join(base_dir, "lambda_function.zip")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(lambda_file, arcname="lambda_function.py")

        # Inclui PIL e pillow.libs do venv local (Linux x86_64 cp312) para processamento real de imagem
        site_packages_candidates = [
            os.path.join(base_dir, "venv", "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"),
            os.path.join(base_dir, "venv", "lib", "python3.12", "site-packages"),
        ]
        for sp in site_packages_candidates:
            if os.path.isdir(sp):
                for pkg_dir in ("PIL", "pillow.libs"):
                    full_pkg = os.path.join(sp, pkg_dir)
                    if os.path.isdir(full_pkg):
                        for root, _, files in os.walk(full_pkg):
                            for file in files:
                                abs_path = os.path.join(root, file)
                                rel_path = os.path.relpath(abs_path, sp)
                                zf.write(abs_path, arcname=rel_path)
                break

    zip_bytes = buf.getvalue()
    with open(zip_path, "wb") as f:
        f.write(zip_bytes)
    print(f"[Lambda] Pacote 'lambda_function.zip' gerado ({len(zip_bytes) / 1024:.1f} KB).")
    return zip_bytes


def configurar_lambda_e_gatilho_s3():
    """
    Faz o deploy da função AWS Lambda 'processar-imagem-s3' e configura
    o gatilho (Event Notification) no bucket 'galeria-imagens' (Atividade #3).
    """
    lambda_client = get_client("lambda")
    s3 = get_client("s3")
    zip_bytes = empacotar_lambda()

    try:
        lambda_client.get_function(FunctionName=LAMBDA_NAME)
        print(f"[Lambda] Atualizando código da função '{LAMBDA_NAME}'...")
        lambda_client.update_function_code(
            FunctionName=LAMBDA_NAME,
            ZipFile=zip_bytes,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"[Lambda] Criando função '{LAMBDA_NAME}'...")
            lambda_client.create_function(
                FunctionName=LAMBDA_NAME,
                Runtime="python3.12",
                Role=LAMBDA_ROLE,
                Handler="lambda_function.lambda_handler",
                Code={"ZipFile": zip_bytes},
                Timeout=30,
                MemorySize=256,
                Environment={
                    "Variables": {
                        "PROCESSED_BUCKET": BUCKET_PROCESSADAS,
                    }
                },
            )
        else:
            raise

    # Aguarda a função Lambda ficar no estado Active
    for _ in range(30):
        info = lambda_client.get_function_configuration(FunctionName=LAMBDA_NAME)
        state = info.get("State", "Active")
        if state == "Active":
            break
        time.sleep(1)

    function_arn = info["FunctionArn"]
    print(f"[Lambda] Função '{LAMBDA_NAME}' ativa! ARN: {function_arn}")

    # Concede permissão para o S3 invocar a função Lambda
    try:
        lambda_client.add_permission(
            FunctionName=LAMBDA_NAME,
            StatementId="s3-trigger-permission",
            Action="lambda:InvokeFunction",
            Principal="s3.amazonaws.com",
            SourceArn=f"arn:aws:s3:::{BUCKET_ORIGEM}",
        )
    except ClientError:
        pass  # Permissão já adicionada anteriormente

    # Configura a notificação de eventos do S3 (s3:ObjectCreated:*) para acionar a Lambda
    s3.put_bucket_notification_configuration(
        Bucket=BUCKET_ORIGEM,
        NotificationConfiguration={
            "LambdaFunctionConfigurations": [
                {
                    "Id": "AcionarLambdaNoUploadS3",
                    "LambdaFunctionArn": function_arn,
                    "Events": ["s3:ObjectCreated:*"],
                }
            ]
        },
    )
    print(f"[S3 -> Lambda] Gatilho s3:ObjectCreated:* configurado no bucket '{BUCKET_ORIGEM}' -> '{LAMBDA_NAME}'.")


def inicializar_infraestrutura():
    print("=" * 60)
    print("Inicializando infraestrutura AWS no LocalStack...")
    print("=" * 60)
    configurar_s3()
    configurar_dynamodb()
    configurar_lambda_e_gatilho_s3()
    print("=" * 60)
    print("Infraestrutura pronta para as Atividades #1, #2 e #3!")
    print("=" * 60)


if __name__ == "__main__":
    inicializar_infraestrutura()
