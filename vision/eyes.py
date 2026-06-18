import os
import google.generativeai as genai
from dotenv import load_dotenv

def look_at_screen() -> str:
    """Takes a screenshot of the user's screen, analyzes it using Gemini Vision, and returns a detailed text description of what is currently visible."""
    try:
        import mss
        from PIL import Image
    except ImportError:
        return "Error: Screen capture libraries (mss, Pillow) are not installed on this system, sir."
        
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Save temporarily
            img_path = "temp_screen.png"
            img.save(img_path)
            
            # Analyze with Gemini
            load_dotenv()
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return "Error: Cannot see. GEMINI_API_KEY is missing."
            genai.configure(api_key=api_key)
            
            model = genai.GenerativeModel("gemini-2.5-flash")
            
            # Upload image to Gemini
            image_file = genai.upload_file(img_path)
            response = model.generate_content([
                image_file, 
                "You are J.A.R.V.I.S's ocular sensor. Describe in precise detail everything visible on this screen. Mention application names, visible text, layout, and overall context."
            ])
            
            # Cleanup
            os.remove(img_path)
            try:
                genai.delete_file(image_file.name)
            except Exception:
                pass
            
            return f"Current Screen Contents:\n{response.text}"
            
    except Exception as e:
        return f"Error capturing or analyzing screen visually: {str(e)}"

VISION_TOOLS = [look_at_screen]
