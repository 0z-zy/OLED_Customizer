from PIL import Image, ImageDraw

def truncate_text(font, text, max_width):
    if not text: return ""
    
    # Check if fits (rough check)
    if font.getlength(text) <= max_width:
        return text
        
    # Truncate
    for i in range(len(text), 0, -1):
        sub = text[:i] + "..."
        if font.getlength(sub) <= max_width:
            return sub
    return "..."

class MarqueeText:
    def __init__(self, font, width, text=""):
        self.font = font
        self.width = width
        self.text = text
        self.offset = 0
        self.max_width = 0
        self._update_metrics()
        
    def set_text(self, text):
        if self.text != text:
             self.text = text
             self.offset = 0
             self._update_metrics()
             
    def _update_metrics(self):
        self.text_width = self.font.getlength(self.text)
        # Add some padding for loop
        self.total_width = self.text_width + 20 

    def next_step(self, fps, is_playing):
        if not is_playing:
            return
            
        if self.text_width <= self.width:
            self.offset = 0
            return
            
        # Move offset
        speed = 20 # pixels per second?
        step = speed / fps
        self.offset += step
        
        if self.offset > self.total_width:
            self.offset = 0
            
    def get_image(self):
        # Create image
        img = Image.new("1", (self.width, 20), 0) # 20px height enough?
        draw = ImageDraw.Draw(img)
        
        if self.text_width <= self.width:
             # Center or Left? Left usually.
             draw.text((0, 0), self.text, font=self.font, fill=1)
        else:
             # Draw scrolling
             x = -int(self.offset)
             draw.text((x, 0), self.text, font=self.font, fill=1)
             
             # Draw repeat
             if x + self.total_width < self.width:
                 draw.text((x + self.total_width, 0), self.text, font=self.font, fill=1)
                 
        return img
