FROM node:22-slim AS frontend

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build:css


# Use an official Python image as the runtime base
FROM python:3.14.3-slim

# Set the working directory in the container
WORKDIR /modulearn

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files into the container
COPY . .

# Copy the generated stylesheet without carrying Node into the runtime image
COPY --from=frontend /build/static/css/tailwind.generated.css ./static/css/tailwind.generated.css

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=modulearn.settings

# Expose the port that Django runs on
EXPOSE 8000

COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

CMD ["./docker-entrypoint.sh"]
