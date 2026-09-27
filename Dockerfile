# Wall Street Service Lambda
# Python 3.12 on AWS Lambda

FROM public.ecr.aws/lambda/python:3.12

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy requirements first for better caching
# (runtime deps only -- test/lint tooling is in requirements-dev.txt and must NOT ship in this image)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set the handler
CMD ["src.index.lambda_handler"]
