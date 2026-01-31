# Earnings Prediction 404 Error - Fix Documentation

## Problem

Users were getting 404 errors when trying to submit earnings predictions in the iOS app.

## Root Cause

There was a **routing mismatch** between the iOS app and the wall-street Lambda backend:

### iOS App Expected Format
- **Endpoint**: `POST /wall-street/earnings/predict/{ticker}`
- **Example**: `POST /wall-street/earnings/predict/AAPL`
- **Body**:
  ```json
  {
    "eventId": "AAPL",
    "prediction": "beat"
  }
  ```

### Backend Original Implementation
- **Endpoint**: `POST /wall-street/earnings/predict`
- **Body**:
  ```json
  {
    "ticker": "AAPL",
    "prediction": "BEAT"
  }
  ```

The iOS app was sending the ticker in the URL path (`/wall-street/earnings/predict/AAPL`), but the backend was only configured to handle `/wall-street/earnings/predict` and expected the ticker in the request body.

## Solution

Updated the wall-street Lambda service to support **both formats**:

### 1. Route Handler Update (src/index.py)

Changed from:
```python
if path == "/wall-street/earnings/predict" and http_method == "POST":
    _require_auth(user_id)
    return submit_earnings_prediction(
        user_id=user_id,
        ticker=body.get("ticker"),
        prediction=body.get("prediction"),
    )
```

To:
```python
# Support both /wall-street/earnings/predict/{ticker} (iOS format) and /wall-street/earnings/predict (body format)
if path.startswith("/wall-street/earnings/predict") and http_method == "POST":
    _require_auth(user_id)
    # Extract ticker from path if present, otherwise from body
    ticker = None
    if path.startswith("/wall-street/earnings/predict/"):
        ticker = path_params.get("ticker") or path.split("/")[-1]
    if not ticker:
        # Support both "ticker" and "eventId" (iOS uses eventId as ticker)
        ticker = body.get("ticker") or body.get("eventId")

    return submit_earnings_prediction(
        user_id=user_id,
        ticker=ticker,
        prediction=body.get("prediction"),
    )
```

### 2. Input Validation (src/handlers/earnings.py)

Added validation to ensure required fields are present:
```python
def submit_earnings_prediction(
    user_id: str,
    ticker: str,
    prediction: str,
) -> dict:
    """Submit an earnings prediction.

    POST /wall-street/earnings/predict
    POST /wall-street/earnings/predict/{ticker}
    """
    from src.utils.errors import ValidationError

    # Validate required fields
    if not ticker:
        raise ValidationError("Ticker is required", field="ticker")
    if not prediction:
        raise ValidationError("Prediction is required", field="prediction")

    service = EarningsService()
    # ... rest of implementation
```

## Supported Formats

The endpoint now supports **three different formats** for maximum compatibility:

1. **iOS Format (Ticker in Path)**
   - `POST /wall-street/earnings/predict/AAPL`
   - Body: `{"eventId": "AAPL", "prediction": "beat"}`

2. **Body Format with `ticker`**
   - `POST /wall-street/earnings/predict`
   - Body: `{"ticker": "AAPL", "prediction": "BEAT"}`

3. **Body Format with `eventId`**
   - `POST /wall-street/earnings/predict`
   - Body: `{"eventId": "AAPL", "prediction": "beat"}`

## Case Insensitivity

The service already handles case-insensitive predictions (line 81 in `earnings.py`):
```python
pred_type = EarningsPredictionType(prediction_type.upper())
```

So both `"beat"` and `"BEAT"` are accepted.

## Files Modified

1. `/Users/abdulbashirabdulzahir/Desktop/TRADESTREAK/wall-street-service/src/index.py`
2. `/Users/abdulbashirabdulzahir/Desktop/TRADESTREAK/wall-street-service/src/handlers/earnings.py`

## Deployment

To deploy the fix:

1. **Commit the changes**:
   ```bash
   cd /Users/abdulbashirabdulzahir/Desktop/TRADESTREAK/wall-street-service
   git add src/index.py src/handlers/earnings.py
   git commit -m "fix: Support iOS earnings prediction endpoint format

   - Add support for /wall-street/earnings/predict/{ticker} format
   - Accept both 'ticker' and 'eventId' in request body
   - Add input validation for required fields
   - Maintain backward compatibility with existing formats"
   ```

2. **Push to trigger deployment**:
   ```bash
   git push origin main
   ```

   This will automatically trigger the GitHub Actions workflow (`.github/workflows/deploy.yml`) which will:
   - Build the Docker image
   - Push to ECR
   - Update the Lambda function

3. **Verify deployment**:
   - Check GitHub Actions for successful deployment
   - Test the endpoint from the iOS app
   - Monitor CloudWatch logs at `/aws/lambda/tradestreak-wall-street`

## Testing

After deployment, verify the fix works by:

1. Opening the TradeStreak iOS app
2. Navigate to Wall Street > Earnings Predictions
3. Select an upcoming earnings event
4. Submit a prediction (Beat/Meet/Miss)
5. Verify the prediction is saved successfully

The error should be resolved and predictions should work without 404 errors.

## Additional Notes

- The API Gateway is correctly configured to route `/wall-street/{proxy+}` to the wall-street Lambda
- The wall-street Lambda function name is `tradestreak-wall-street`
- The DynamoDB table used is `tradestreak-wall-street`
- The Lambda has proper IAM permissions for DynamoDB access
- EventBridge schedules are in place for earnings data ingestion

## Related Infrastructure

- **Terraform Config**: `/Users/abdulbashirabdulzahir/Desktop/TRADESTREAK/tradestreak/tradestreak/terraform-infrastructure/lambda_wall_street.tf`
- **API Gateway**: Configured with proxy integration at `/wall-street/{proxy+}`
- **Authentication**: Cognito User Pools authorizer is enabled for all wall-street endpoints
