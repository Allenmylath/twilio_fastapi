from twilio.rest import Client
import os

def get_call_details(call_sid):
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    
    if not account_sid or not auth_token:
        raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set in environment variables")
        
    client = Client(account_sid, auth_token)
    
    try:
        call = client.calls(call_sid).fetch()
        
        if call.from_formatted:
            number_info = client.lookups.v2.phone_numbers(call.from_formatted).fetch(
                fields=['line_type_intelligence', 'caller_name']
            )
            
            result = {
                'phone_number': call.from_formatted,
                'to_number': call.to_formatted,
                'duration': call.duration,
                'status': call.status,
                'direction': call.direction,
                'start_time': str(call.start_time),
                'end_time': str(call.end_time),
                'line_type': number_info.line_type_intelligence.get('type', 'Unknown'),
                'caller_name': number_info.caller_name.get('caller_name', 'Unknown') if number_info.caller_name else 'Unknown'
            }
        else:
            result = {
                'phone_number': 'Unknown',
                'to_number': call.to_formatted,
                'duration': call.duration,
                'status': call.status,
                'direction': call.direction,
                'start_time': str(call.start_time),
                'end_time': str(call.end_time),
                'line_type': 'Unknown',
                'caller_name': 'Unknown'
            }
            
        return result
        
    except Exception as e:
        raise Exception(f"Error retrieving call details: {str(e)}")
