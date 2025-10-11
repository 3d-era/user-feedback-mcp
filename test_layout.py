#!/usr/bin/env python3
"""
Script để test layout mới của User Feedback UI
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from feedback_ui import feedback_ui

if __name__ == "__main__":
    # Test với project directory hiện tại
    project_dir = os.getcwd()
    prompt = "🎉 ĐÃ HOÀN THÀNH TẤT CẢ:\n\n✅ 1. Chunk-based translation\n   - Split content thành 2 chunks (~2000 chars/chunk)\n   - Tránh Monica token limit truncation\n   - 31/31 images preserved (thay vì 8/31)\n\n✅ 2. Image placeholder protection\n   - Extract images → placeholders trước translate\n   - Restore images sau translate\n   - 28/30 images downloaded (2 là placeholder \"Image Not Available\")\n   - 26/28 images replaced với CDN URLs\n\n✅ 3. Table conversion\n   - Added TableConverter từ league/html-to-markdown\n   - Tables converted sang Markdown table syntax\n   - 51 pipes detected (Markdown tables)\n   - Tables có images bên trong work perfect\n\n✅ 4. Monica system message updated\n   - Preserve Markdown syntax\n   - Preserve placeholders\n   - Không wrap content trong HTML tags\n\n✅ 5. Links không bị escape\n   - https://www.reddit.com/r/honeycombwall/ ✅\n\n⏱️ Performance: 90 giây (thay vì 20 giây)\n   - Do translate 2 chunks riêng biệt\n   - Trade-off acceptable cho quality\n\n📝 Files modified:\n   - MarkdownConverter.php: Added TableConverter, image placeholders\n   - ContentProcessorService.php: Chunk-based translation\n   - MonicaTranslator.php: Updated system message\n\nPa test thử xem content hiển thị có OK không?"
    
    print(f"Testing UI with project directory: {project_dir}")
    print(f"Prompt: {prompt}")
    
    result = feedback_ui(project_dir, prompt)
    
    if result:
        print("\n=== RESULT ===")
        print(f"User Feedback: {result['user_feedback']}")
        print(f"\nCommand Logs:\n{result['logs']}")
    else:
        print("\nUI was closed without submitting feedback")

