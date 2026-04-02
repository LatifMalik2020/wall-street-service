# Wall Street Service Runbooks

## Deploy (via GitHub Actions)
Push to `main` branch triggers automatic deployment. Manual deploy:
```bash
docker build -t wall-street-service .
aws ecr get-login-password | docker login --username AWS --password-stdin 588699680231.dkr.ecr.us-east-1.amazonaws.com
docker tag wall-street-service:latest 588699680231.dkr.ecr.us-east-1.amazonaws.com/tradestreak-wall-street:latest
docker push 588699680231.dkr.ecr.us-east-1.amazonaws.com/tradestreak-wall-street:latest
aws lambda update-function-code --function-name tradestreak-wall-street --image-uri 588699680231.dkr.ecr.us-east-1.amazonaws.com/tradestreak-wall-street:latest
```

## Check Data Freshness
```bash
# Latest congress trades
aws dynamodb query --table-name <table> --key-condition-expression "pk = :pk" --expression-attribute-values '{":pk":{"S":"CONGRESS"}}' --scan-index-forward false --limit 1
```

## Check Logs
```bash
aws logs tail /aws/lambda/tradestreak-wall-street --since 10m --follow
```

## FMP Rate Limit Issues
- Free: 250 calls/day. Starter ($25/mo): 300 calls/min.
- If rate limited, EventBridge jobs will fail silently. Check CloudWatch for 429 errors.
