import PyPDF2

def read_pdf(file_path):
    """
    Read a PDF file and return its text content as a string.
    
    Parameters:
        file_path (str): Path to the PDF file
        
    Returns:
        str: Extracted text from the PDF
        
    Raises:
        FileNotFoundError: If the PDF file is not found
        PyPDF2.PdfReadError: If there's an error reading the PDF
    """
    try:
        # Open the PDF file in binary read mode
        with open(file_path, 'rb') as file:
            # Create a PDF reader object
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Initialize an empty string to store the text
            text = ""
            
            # Iterate through all pages and extract text
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            return text.strip()
            
    except FileNotFoundError:
        raise FileNotFoundError(f"PDF file not found at path: {file_path}")
    except PyPDF2.PdfReadError as e:
        raise PyPDF2.PdfReadError(f"Error reading PDF file: {str(e)}")
    except Exception as e:
        raise Exception(f"An unexpected error occurred: {str(e)}")


