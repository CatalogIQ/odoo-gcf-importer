# CatalogIQ to Odoo Product Synchronization

This repository contains an example Google Cloud Function designed to synchronize products from CatalogIQ to Odoo via the RPC-API. It is triggered by a Pub/Sub message.

## Functionality

The function is triggered by a Pub/Sub message with the schema `{'offset': int}`. It fetches products from the CatalogIQ API using the provided offset and adds them to the Odoo Catalog API. If a product with the same name and/or SKU already exists in Odoo it will add another. You can implement logic to check for exisitng records by the default_code

## Requirements

- Google Cloud Console Developer Account with Billing Enabled
- Enabled Google Cloud services: Cloud Functions, Pub/Sub, and Cloud Run
- Basic knowledge of Python
- Odoo store with XML-API access
- Odoo Username and Password

### Alternative Usage

You can modify this function to process specific records by `template_id` or the date created/updated, making it possible to trigger imports directly from a Google Sheet containing product IDs and details via an HTTP function.

### Setting up Pub/Sub

1. Navigate to Pub/Sub in the Google Cloud Console.
2. Create a new topic.
3. Enter the desired topic name.
4. Add a schema with the property `offset` as a String.
5. Save your topic configuration.
6. Click "+Trigger Cloud Function" to connect your function.


### Configuring Cloud Function

1. Set the function name and runtime to Python 3.12.
2. Configure the number of messages to process at a time to `1`.
3. Visit the [project repository](https://github.com/CatalogIQ/odoo-gcf-importer).
4. In the Cloud Function Inline Editor, copy the contents of `Requirements.txt` and `Main.py` from the src directory.
6. Set the `entry_point` to `main`.
7. Set the following environment variables:
    - `CATALOGIQ_API_KEY`: Your CatalogIQ API key.
    - `ODOO_URL`: Your Odoo app url ie `https://mystore.com`
    - `ODOO_DB`: Your Odoo database name
    - `ODOO_USERNAME`: Your Odoo username
    - `ODOO_PASSWORD`: Your Odoo password
8. Deploy the function.

## Usage

Publish a test message to the Pub/Sub topic with the schema `{'offset': string}` to trigger the function. The function will fetch products from the CatalogIQ API starting from the provided offset and synchronize them to the BigCommerce Catalog API.

## Disclaimer

This function is provided as an example to help you get started with your own implementation. There are no warranties or guarantees provided with this code.

## Contributing

Contributions are welcome! Please feel free to submit a pull request.

## License

This project is licensed under the terms of the MIT license.