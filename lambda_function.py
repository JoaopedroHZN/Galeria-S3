import io
import os
import json
import urllib.parse
import boto3

# Bucket de destino para as imagens processadas pela Lambda (Atividade #3)
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "galeria-processadas")


def get_s3_client():
    """
    Cria o cliente S3 apontando para o LocalStack.
    Dentro do container da Lambda, o LocalStack injeta AWS_ENDPOINT_URL ou LOCALSTACK_HOSTNAME
    para que a função consiga se comunicar com o container principal na porta 4566.
    """
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    if not endpoint_url and os.environ.get("LOCALSTACK_HOSTNAME"):
        edge_port = os.environ.get("EDGE_PORT", "4566")
        endpoint_url = f"http://{os.environ['LOCALSTACK_HOSTNAME']}:{edge_port}"
    if not endpoint_url:
        endpoint_url = "http://localhost:4566"

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def processar_imagem_bytes(image_bytes: bytes, filename: str):
    """
    Processa a imagem recebida do bucket de origem:
    1. Converte a imagem para Escala de Cinza (Preto e Branco - modo 'L' -> 'RGB')
       e aplica filtro de autocontraste/borda usando Pillow (PIL).
    2. Retorna os bytes processados, o Content-Type e os metadados do processamento.
    """
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(image_bytes)) as img:
            formato_original = img.format or "PNG"
            largura, altura = img.size

            # Converte para escala de cinza (Grayscale) e aplica autocontraste
            img_gray = ImageOps.grayscale(img)
            img_processada = ImageOps.autocontrast(img_gray)

            # Adiciona uma moldura sutil para evidenciar visualmente o processamento Serverless
            img_final = ImageOps.expand(img_processada.convert("RGB"), border=6, fill="#0066cc")

            output = io.BytesIO()
            formato_saida = formato_original if formato_original in ("JPEG", "PNG", "WEBP", "BMP") else "PNG"
            img_final.save(output, format=formato_saida)
            output.seek(0)

            content_type = f"image/{formato_saida.lower()}"
            metadados = {
                "processado-por": "aws-lambda-localstack",
                "efeito-aplicado": "grayscale-autocontrast-border",
                "dimensoes-originais": f"{largura}x{altura}",
                "dimensoes-finais": f"{img_final.width}x{img_final.height}",
                "tamanho-original-bytes": str(len(image_bytes)),
            }
            return output.read(), content_type, metadados
    except Exception as exc:
        # Fallback caso a imagem seja um formato não suportado pelo Pillow
        metadados = {
            "processado-por": "aws-lambda-localstack-fallback",
            "efeito-aplicado": "copia-verificada",
            "tamanho-original-bytes": str(len(image_bytes)),
            "observacao": str(exc)[:100],
        }
        return image_bytes, "application/octet-stream", metadados


def lambda_handler(event, context):
    """
    Handler principal da função AWS Lambda (Atividade #3).
    Acionado automaticamente pelo evento s3:ObjectCreated:* quando um arquivo
    é enviado para o bucket 'galeria-imagens'.
    """
    s3 = get_s3_client()
    resultados = []

    for record in event.get("Records", []):
        source_bucket = record["s3"]["bucket"]["name"]
        object_key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        print(f"[Lambda] Evento S3 recebido: bucket={source_bucket}, key={object_key}")

        # 1. Faz o download da imagem original a partir do bucket de origem
        response = s3.get_object(Bucket=source_bucket, Key=object_key)
        original_bytes = response["Body"].read()

        # 2. Processa a imagem (conversão para Preto e Branco + Autocontraste + Moldura)
        processed_bytes, content_type, metadata = processar_imagem_bytes(original_bytes, object_key)

        # 3. Salva a imagem processada no bucket de destino ('galeria-processadas')
        processed_key = f"proc_{object_key}"
        s3.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=processed_key,
            Body=processed_bytes,
            ContentType=content_type,
            Metadata=metadata,
        )

        print(f"[Lambda] Imagem processada salva com sucesso em s3://{PROCESSED_BUCKET}/{processed_key}")
        resultados.append({
            "source_bucket": source_bucket,
            "source_key": object_key,
            "destination_bucket": PROCESSED_BUCKET,
            "destination_key": processed_key,
            "metadata": metadata,
        })

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Processamento concluído com sucesso pela AWS Lambda!",
            "processed_files": resultados,
        }),
    }
