from core.config import save_credentials

def main():
    print("=== أداة إعداد AuraGram ===")

    try:
        api_id_input = input("الصق App api_id (الرقم) واضغط Enter: ").strip()
        api_id = int(api_id_input)

        api_hash = input("الصق App api_hash (النص الطويل) واضغط Enter: ").strip()

        save_credentials(api_id, api_hash)

        print("\nتم حفظ الإعدادات بنجاح في ملف config.json!")
        print("يمكنك الآن تشغيل البرنامج الأساسي main.py")

    except ValueError:
        print("\nخطأ: الـ API_ID يجب أن يكون أرقام فقط. يرجى إعادة المحاولة.")

if __name__ == "__main__":
    main()
