from hubspot import HubSpot
from hubspot.crm.contacts import SimplePublicObjectInputForCreate, ApiException
from hubspot.crm.deals import SimplePublicObjectInputForCreate as DealInput
from flask import current_app
from datetime import datetime
import difflib

class HubSpotClient:
    """Handles HubSpot CRM operations"""
    
    def __init__(self):
        """Initialize HubSpot client"""
        api_key = current_app.config['HUBSPOT_API_KEY']
        if not api_key:
            raise ValueError("HubSpot API key must be configured")
        
        self.client = HubSpot(access_token=api_key)
    
    def search_contacts_by_name(self, name, limit=10):
        """
        Search for contacts by name (fuzzy matching)
        Returns: list of matching contacts
        """
        try:
            # Search using HubSpot search API
            search_request = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "firstname",
                                "operator": "CONTAINS_TOKEN",
                                "value": name.split()[0] if name else ""
                            }
                        ]
                    }
                ],
                "properties": [
                    "firstname", "lastname", "email", "address", 
                    "city", "state", "zip", "phone", "hs_object_id"
                ],
                "limit": limit
            }
            
            response = self.client.crm.contacts.search_api.do_search(
                public_object_search_request=search_request
            )
            
            return [
                {
                    'id': contact.id,
                    'name': f"{contact.properties.get('firstname', '')} {contact.properties.get('lastname', '')}".strip(),
                    'address': contact.properties.get('address', ''),
                    'city': contact.properties.get('city', ''),
                    'state': contact.properties.get('state', ''),
                    'zip': contact.properties.get('zip', ''),
                    'phone': contact.properties.get('phone', ''),
                    'email': contact.properties.get('email', ''),
                    'account_number': contact.properties.get('hs_object_id', '')
                }
                for contact in response.results
            ]
        except ApiException as e:
            current_app.logger.error(f"HubSpot API error: {e}")
            return []
    
    def search_contacts_by_address(self, address, city=None, state=None, limit=10):
        """
        Search for contacts by address
        Returns: list of matching contacts
        """
        try:
            filters = [
                {
                    "propertyName": "address",
                    "operator": "CONTAINS_TOKEN",
                    "value": address
                }
            ]
            
            if city:
                filters.append({
                    "propertyName": "city",
                    "operator": "EQ",
                    "value": city
                })
            
            if state:
                filters.append({
                    "propertyName": "state",
                    "operator": "EQ",
                    "value": state
                })
            
            search_request = {
                "filterGroups": [{"filters": filters}],
                "properties": [
                    "firstname", "lastname", "email", "address",
                    "city", "state", "zip", "phone", "hs_object_id"
                ],
                "limit": limit
            }
            
            response = self.client.crm.contacts.search_api.do_search(
                public_object_search_request=search_request
            )
            
            return [
                {
                    'id': contact.id,
                    'name': f"{contact.properties.get('firstname', '')} {contact.properties.get('lastname', '')}".strip(),
                    'address': contact.properties.get('address', ''),
                    'city': contact.properties.get('city', ''),
                    'state': contact.properties.get('state', ''),
                    'zip': contact.properties.get('zip', ''),
                    'phone': contact.properties.get('phone', ''),
                    'email': contact.properties.get('email', ''),
                    'account_number': contact.properties.get('hs_object_id', '')
                }
                for contact in response.results
            ]
        except ApiException as e:
            current_app.logger.error(f"HubSpot API error: {e}")
            return []
    
    def fuzzy_match_contacts(self, check_name, check_address, candidates):
        """
        Perform fuzzy matching on contact candidates
        Returns: best match with confidence score
        """
        if not candidates:
            return None, "none"
        
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            # Calculate name similarity
            name_similarity = difflib.SequenceMatcher(
                None, 
                check_name.lower(), 
                candidate['name'].lower()
            ).ratio()
            
            # Calculate address similarity
            address_similarity = 0
            if check_address and candidate['address']:
                address_similarity = difflib.SequenceMatcher(
                    None,
                    check_address.lower(),
                    candidate['address'].lower()
                ).ratio()
            
            # Combined score (weighted)
            score = (name_similarity * 0.6) + (address_similarity * 0.4)
            
            if score > best_score:
                best_score = score
                best_match = candidate
        
        # Determine confidence
        if best_score >= 0.9:
            confidence = "exact"
        elif best_score >= 0.7:
            confidence = "fuzzy"
        else:
            confidence = "low"
        
        return best_match, confidence
    
    def create_contact(self, name, address, city, state, zip_code, phone=None, email=None):
        """
        Create a new contact in HubSpot
        Returns: contact ID
        """
        try:
            # Split name into first/last
            name_parts = name.split(maxsplit=1)
            firstname = name_parts[0] if len(name_parts) > 0 else name
            lastname = name_parts[1] if len(name_parts) > 1 else ""
            
            properties = {
                "firstname": firstname,
                "lastname": lastname,
                "address": address or "",
                "city": city or "",
                "state": state or "",
                "zip": zip_code or "",
            }
            
            if phone:
                properties["phone"] = phone
            
            if email:
                properties["email"] = email
            
            contact_input = SimplePublicObjectInputForCreate(properties=properties)
            response = self.client.crm.contacts.basic_api.create(
                simple_public_object_input_for_create=contact_input
            )
            
            return response.id
        except ApiException as e:
            current_app.logger.error(f"Error creating contact: {e}")
            raise
    
    def create_deal(self, check_data, batch_data, contact_id):
        """
        Create a deal in HubSpot
        Returns: deal ID
        """
        try:
            # Prepare deal properties
            properties = {
                "dealname": check_data['payee_name'],
                "pipeline": "Gifts",  # TODO: Make configurable
                "dealstage": "closedwon",
                "amount": str(check_data['amount']),
                "closedate": datetime.now().isoformat(),
                "check_date": check_data['check_date'].isoformat() if check_data.get('check_date') else None,
                "check_number": check_data.get('check_number', ''),
                "batch_number": batch_data['batch_number'],
                "payment_method": "Check",
                "appeal": batch_data['appeal_type'],
                "appeal_code": batch_data['appeal_code'],
                "postmark_year": str(datetime.now().year),
            }
            
            # Remove None values
            properties = {k: v for k, v in properties.items() if v is not None}
            
            deal_input = DealInput(properties=properties)
            response = self.client.crm.deals.basic_api.create(
                simple_public_object_input_for_create=deal_input
            )
            
            # Associate deal with contact
            if contact_id:
                self.associate_deal_to_contact(response.id, contact_id)
            
            return response.id
        except ApiException as e:
            current_app.logger.error(f"Error creating deal: {e}")
            raise
    
    def associate_deal_to_contact(self, deal_id, contact_id):
        """Associate a deal with a contact"""
        try:
            self.client.crm.deals.associations_api.create(
                deal_id=deal_id,
                to_object_type="contacts",
                to_object_id=contact_id,
                association_type="deal_to_contact"
            )
        except ApiException as e:
            current_app.logger.error(f"Error associating deal to contact: {e}")
            raise
    
    def update_deal(self, deal_id, properties):
        """Update an existing deal"""
        try:
            self.client.crm.deals.basic_api.update(
                deal_id=deal_id,
                simple_public_object_input={"properties": properties}
            )
        except ApiException as e:
            current_app.logger.error(f"Error updating deal: {e}")
            raise
