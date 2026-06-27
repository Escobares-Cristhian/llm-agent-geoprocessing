# 0) Make sure your Cloud project is registered for Earth Engine and EE API is enabled
#    (EE docs require project registration + API enabled).

# 1) Create a service account
gcloud iam service-accounts create gee-plugin --display-name="GEE Plugin SA" --project ee-cristhianescobares

# 2) Grant minimum Earth Engine role
# Viewer may be enough for reads, but thumbnails/maps can require "create",
# so if you hit PERMISSION_DENIED for thumbnails/maps, use writer instead.
gcloud projects add-iam-policy-binding ee-cristhianescobares \
  --member="serviceAccount:gee-plugin@ee-cristhianescobares.iam.gserviceaccount.com" \
  --role="roles/earthengine.writer"

# 3) Create a key (this produces the JSON)
gcloud iam service-accounts keys create ./gee-sa.json \
  --iam-account "gee-plugin@ee-cristhianescobares.iam.gserviceaccount.com" \
  --project ee-cristhianescobares

