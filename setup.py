import json
import os

def main():
    print("=== أداة إعداد AuraGram ===")
    
    try:
        api_id_input = input("الصق App api_id (الرقم) واضغط Enter: ").strip()
        api_id = int(api_id_input)
        
        api_hash = input("الصق App api_hash (النص الطويل) واضغط Enter: ").strip()
        
        config_data = {
            "API_ID": api_id,
            "API_HASH": api_hash
        }
        
        with open("config.json", "w", encoding="utf-8") as file:
            json.dump(config_data, file, indent=4)
            
        print("\nتم حفظ الإعدادات بنجاح في ملف config.json!")
        print("يمكنك الآن تشغيل البرنامج الأساسي main.py")
        
    except ValueError:
        print("\nخطأ: الـ API_ID يجب أن يكون أرقام فقط. يرجى إعادة المحاولة.")

if __name__ == "__main__":
    main()