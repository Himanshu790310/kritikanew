#!/bin/bash

# Build and push image
gcloud builds submit --tag gcr.io/$GOOGLE_CLOUD_PROJECT/kritikanew1

# Deploy to Cloud Run
gcloud run deploy kritikanew1 \
  --image gcr.io/$GOOGLE_CLOUD_PROJECT/kritikanew1 \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars="TELEGRAM_BOT_TOKEN=7833059587:AAGWCrFoYJqaIy51BHHRVtNrimJbZGTMows,GOOGLE_API_KEY=AIzaSyDc6wrTkV2k4AWl72NZxET6URrXCbM8haM,WEBHOOK_URL=https://kritikanew1-494584189423.europe-west1.run.app/webhook" \
  --port 8080 \
  --timeout 300 \
  --cpu 1 \
  --memory 1Gi

# Set webhook
SERVICE_URL=$(gcloud run services describe kritikanew1 --platform managed --region europe-west1 --format 'value(status.url)')
curl -X POST \
  "https://api.telegram.org/bot7833059587:AAGWCrFoYJqaIy51BHHRVtNrimJbZGTMows/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${SERVICE_URL}/webhook\"}"
