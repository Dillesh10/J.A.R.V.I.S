import os
from dotenv import load_dotenv  # type: ignore

def look_at_screen() -> str:
    """Takes a screenshot of the user's screen, analyzes it using the central vision provider, and returns a detailed text description."""
    try:
        import mss  # type: ignore
        from PIL import Image  # type: ignore
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
            
            from core.providers import provider_manager
            prompt = "You are J.A.R.V.I.S's ocular sensor. Describe in precise detail everything visible on this screen. Mention application names, visible text, layout, and overall context."
            
            # Call vision via ProviderManager
            response = provider_manager.vision(
                image_data=img_path,
                prompt=prompt
            )
            
            # Cleanup
            if os.path.exists(img_path):
                os.remove(img_path)
                
            return f"Current Screen Contents:\n{response.content}"
            
    except Exception as e:
        return f"Error capturing or analyzing screen visually: {str(e)}"

VISION_TOOLS = [look_at_screen]
