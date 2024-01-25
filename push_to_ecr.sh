# Description: Pushes the docker image to ECR and updates the lambda function
source .env
version=$1
image_uri=${REPO_ARN}:v$version
echo $image_uri

docker build -t $image_uri . --platform linux/amd64
docker push $image_uri
aws lambda update-function-code \
  --function-name fun_readable \
  --image-uri $image_uri \
  --publish \
  ;