import json
import os
import base64
from xmlrpc import client as xmlrpc_client
import requests
from google.cloud import pubsub_v1

"""
Google Cloud Function triggered by a Pub/Sub message.
Pub/Sub Message Schema: {'offset': int}
Function Entry Point: main
Example by: https://catalogiq.app
Source: https://catalogiq.app/api/v1/products
Destination: Odoo v15 Community Edition via XML-RPC API

This function retrieves product data from CatalogIQ API, creates a product template in Odoo, and updates the SKUs of product variants.
It then publishes a new message to the same Pub/Sub topic with the next offset to process the next product.
It does not handle errors or retries, which should be implemented based on the specific requirements.
It does not use the cloud_functions decorator as in other examples.
The Odoo XML RPC needs to be enabled in the Odoo instance for this function to work. The odoo user will need api access. Open Source and Enterprise versions support XML RPC.
If you have server access you should develop an addon to handle the product data import in a more efficient way. You can use this as your reference.
Print statements have been added and commented our for debugging purposes. You can remove them in production.
"""


# Environment Variables / You can also use Google Secrets Manager to store these values
CATALOGIQ_API_KEY = os.environ.get('CATALOGIQ_API_KEY')
ODOO_URL = os.environ.get('ODOO_URL') # 'https://yourdomain.com'
ODOO_DB = os.environ.get('ODOO_DB') # Your Odoo Database name
ODOO_USERNAME = os.environ.get('ODOO_USERNAME') # Your Odoo username
ODOO_PASSWORD = os.environ.get('ODOO_PASSWORD') # Your Odoo password
PUBSUB_PROJECT = os.environ.get('PUBSUB_PROJECT') # Your Google Cloud Project ID
PUBSUB_TOPIC = os.environ.get('PUBSUB_TOPIC') # Your Pub/Sub Topic ID


# Odoo XML-RPC Setup
common_proxy = xmlrpc_client.ServerProxy('{}/xmlrpc/2/common'.format(ODOO_URL))
uid = common_proxy.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
models_proxy = xmlrpc_client.ServerProxy('{}/xmlrpc/2/object'.format(ODOO_URL))

# Now you can use this function like this:
# execute_odoo_kw('product.template', 'create', [product_template_data])
# @Input:String model: Odoo model name
# @Input:String method: Odoo method name
# @Input:List args: List of arguments for the method
# @Return: Any: Result of the Odoo method, a list of IDs from search and create methods
def execute_odoo_kw(model, method, args):
    return models_proxy.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, model, method, args)



# Publishes the next offset to the Pub/Sub topic
## You can modify this function to add more parameters to the message to control the processing of the next product,
## such as a created_on datefilter to sync new products.
# @Input:String publisher: Google Project ID
# @Input:String topic_path: Pub/Sub topic name
# @Input:String offset: The next offset to process, must be a string
# @Return:None
def publish_next_message(publisher, topic_path, offset):
    data = json.dumps({'offset': offset}).encode('utf-8')
    publisher.publish(topic_path, data)
    return None
    #print(f'Message published for offset {offset}')


# Creates a new attribute in Odoo or retrieves the existing one by name
# @Input:String attribute_name: Name of the attribute
# @Return:int: ID of the attribute
def create_or_get_attribute_id(attribute_name):
    attribute_ids = execute_odoo_kw('product.attribute', 'search', [[['name', '=', attribute_name]]])
    if not attribute_ids:
        return execute_odoo_kw('product.attribute', 'create', [{'name': attribute_name, 'create_variant': 'always'}])
    return attribute_ids[0]

# Creates a new attribute value in Odoo or retrieves the existing one by the attribute value and attribute ID
# @Input:int attribute_id: ID of the attribute in Odoo
# @Input:String value_name: The attribute value
# @Return:int: ID of the attribute value
def create_or_get_attribute_value_id(attribute_id, value_name):
    value_ids = execute_odoo_kw('product.attribute.value', 'search', [[['name', '=', value_name], ['attribute_id', '=', attribute_id]]])
    if not value_ids:
        return execute_odoo_kw('product.attribute.value', 'create', [{'name': value_name, 'attribute_id': attribute_id}])
    return value_ids[0]

# Updates the SKUs of product variants based on the product variant attributes values
# We first search for the product template attribute values based on the attribute names provided in variant attributes in CatalogIQ.
# Each variant is identified by a unique combination of attribute values.
# Images are downloaded and encoded to base64 on the cloud function server so you must allocate enough resources for this.
# Then we update the SKU and Image of the variant, you can additional variant propertie here.
# @Input:int product_template_id: ID of the product template in Odoo
# @Input:dict product_data: Product data response from CatalogIQ API. Requires fields default_code, image, attributes, variants
# @Return:None
def update_variant_skus(product_template_id, product_data):
    """
    Updates the SKUs of product variants based on the product data provided by CatalogIQ.
    
    """
    try:
        for variant in product_data['variants']:
            # Build a search domain to find the variant based on attribute values
            search_domain = [('product_tmpl_id', '=', product_template_id)]
            
            for attribute in variant['attributes']:
                attribute_id = create_or_get_attribute_id(attribute['name'])
                value_id = create_or_get_attribute_value_id(attribute_id, attribute['value'])

                # We need to find the value ids of the attributes in the variant 
                # Get the product.template.attribute.value record for the attribute value
                ptav_ids = execute_odoo_kw('product.template.attribute.value', 'search', [[['product_attribute_value_id', '=', value_id], ['product_tmpl_id', '=', product_template_id]]])
            
                # Add the product.template.attribute.value record to the search domain
                search_domain.append(('product_template_attribute_value_ids', 'in', ptav_ids))
            
            variant_ids = execute_odoo_kw('product.product', 'search', [search_domain])
            # Search for variants matching the attribute values
          
            if not variant_ids:
                print(f'No variant found for {variant["attributes"]}')
                return None
            for variant_id in variant_ids:
                variant_image_url = variant['image'] + '/800x800'  # replace with the actual key for the image url    
                variant_image_base64 = download_and_encode_image(variant_image_url)          
                # Update each found variant with the SKU provided by CatalogIQ
                variant_update = {
                    'default_code': variant['default_code'],                    
                }
                if variant_image_base64:
                    variant_update['image_1920'] = variant_image_base64
                execute_odoo_kw('product.product', 'write', [variant_id, variant_update])
                # print(f'Updated variant ID {res_update} with SKU {variant["default_code"]}')
        return None
    except Exception as e:
        print(f'Error updating variant SKUs: {e}')
        return None

# Extracts all unique variant attribute names from the product data.
# @Input: dict product_data: CatalogIQ product data response.
# @Return: list: A list of unique variant attribute names.
def get_variant_attribute_names(product_data):
    # Initialize an empty list to store unique variant attribute names
    variant_attributes = []

    # Loop through each variant in the product data
    for variant in product_data['variants']:
        # Loop through each attribute in the current variant
        for attribute in variant['attributes']:
            # If the attribute name is not already in the list, add it
            if attribute['name'] not in variant_attributes:
                variant_attributes.append(attribute['name'])

    # Return the list of unique variant attribute names
    return variant_attributes


# Downloads an image from the provided URL and encodes it to base64.
def download_and_encode_image(image_url):
    try:
        response_img = requests.get(image_url, timeout=5)
        image_base64 = base64.b64encode(response_img.content).decode('utf-8')
        return image_base64
    except Exception as e:
        print(f'Error downloading and encoding image: {e}')
        return None

# Adds additional images (extra product media) to the product template in Odoo.
# The images are downloaded from the image URL provided by CatalogIQ and encoded to base64.
# @Input:int product_template_id: ID of the product template in Odoo
# @Input:list images_data: List of image data from CatalogIQ
# @Return:None
def add_product_images(product_template_id, images_data):
    for image_data in images_data:
        image_url = image_data['url'] + '/800x800'  
        image_base64 = download_and_encode_image(image_url)       
        product_image_data = {
            'name': image_data['name'],
            'image_1920': image_base64,
            'product_tmpl_id': product_template_id,
        }
        if image_base64:
            execute_odoo_kw('product.image', 'create', [product_image_data])
        #print(f'Added image {image_data["name"]} to product template ID {product_template_id}')
    return None

# Creates the product template in Odoo based on the product data from CatalogIQ.
# You can modify this function to add more fields to the product template.
# We are assigning a default category, you can add logic to use CatalogIQ catagories or your own.
# ProductImage is adjsuted to 800px on the longest side to save resources.
# Additional images can be added to the product template from the catalogiq image property list.
# @Input: dict product_data: CatalogIQ product data response.
# @Return: int: ID of the created product template.
def create_product_template(product_data):
    attribute_lines = []
    for variant in product_data['variants']:
        for attribute in variant['attributes']:
            attribute_id = create_or_get_attribute_id(attribute['name'])
            value_id = create_or_get_attribute_value_id(attribute_id, attribute['value'])
            #print(f'attribute_id: {attribute_id}, attribute_name: {attribute['name']}, value_id: {value_id}, value: {attribute["value"]}')
            attribute_lines.append((0, 0, {'attribute_id': attribute_id, 'value_ids': [(6, 0, [value_id])]}) )
    
    # We are excluding the attributes that are already part of the variants
    variant_attributes = get_variant_attribute_names(product_data)
    
    for attribute in product_data['attributes']:
        if attribute['name'] not in variant_attributes:
            attribute_id = create_or_get_attribute_id(attribute['name'])
            value_id = create_or_get_attribute_value_id(attribute_id, attribute['value'])
            attribute_lines.append((0, 0, {'attribute_id': attribute_id, 'value_ids': [(6, 0, [value_id])]}) )            

    # make sure attribute_lines does not have duplicates
    # TODO: We should find a better way to handle this

    # Create a dictionary where the keys are the attribute ids and the values are sets of attribute values
    attribute_dict = {}
    for line in attribute_lines:
        attribute_id = line[2]['attribute_id']
        value_ids = line[2]['value_ids'][0][2]
        if attribute_id not in attribute_dict:
            attribute_dict[attribute_id] = set(value_ids)
        else:
            attribute_dict[attribute_id].update(value_ids)

    # Convert the dictionary back to the original format
    attribute_lines = [(0, 0, {'attribute_id': attribute_id, 'value_ids': [(6, 0, list(value_ids))]})
                    for attribute_id, value_ids in attribute_dict.items()]          
    
    image_url = product_data['main_image'] + '/800x800'  
    response_img = requests.get(image_url)
    image_base64 = base64.b64encode(response_img.content).decode('utf-8')

    product_template_data = {
        'name': product_data['name'],
        'type': 'product',
        'image_1920': image_base64,
        'categ_id': 1,  # Default category
        'attribute_line_ids': attribute_lines
    }
    #Create the product template in Odoo
    product_temp_id = execute_odoo_kw('product.template', 'create', [product_template_data])
    # Add additional images to the product template
    if 'images' in product_data:
        add_product_images(product_temp_id, product_data['images'])
    
    return product_temp_id
    

# The entry point for the Cloud Function
# This function processes a product based on the offset provided in the Pub/Sub message.
def main(event, context):
    """Triggered from a message on a Cloud Pub/Sub topic."""
    message_data = json.loads(base64.b64decode(event['data']).decode('utf-8'))
    offset = message_data.get('offset', 0)

    response = requests.get(f'https://catalogiq.app/api/v1/products?offset={offset}&limit=1', headers={'Catalogiq-Api-Key': CATALOGIQ_API_KEY})
    if response.json()['results']:
        
        product_data = response.json()['results'][0]

        product_template_id = create_product_template(product_data)

        update_variant_skus(product_template_id, product_data)

        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PUBSUB_PROJECT, PUBSUB_TOPIC)
        publish_next_message(publisher, topic_path, str(int(offset) + 1))
    
    return f'Processed product complete'



