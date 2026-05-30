from __future__ import annotations

import re
import unicodedata
from typing import Any

CANONICAL_SLAS = {
    "fd_booking_processing": "usually within 24 to 48 working hours",
    "payment_reconciliation": "booking may complete, otherwise refund usually reflects within 5 working days",
    "maturity_payout": "usually within 1 to 3 working days",
    "grievance_response": "within 48 hours",
    "kyc_pending_review": "usually within 24 working hours",
}

DISCLOSURE_COPY = {
    "recording": "This call may be recorded for quality purposes.",
    "fd": "Stable Money is a distributor. FDs are held directly with the RBI-regulated partner bank and are insured up to 5 lakh rupees per depositor per bank under DICGC. FDs are not regulated by SEBI and are outside the SCORES and Exchange Arbitration framework.",
    "mutual_fund": "Mutual fund investments are subject to market risks. Please read all scheme related documents carefully. Stable Finserv Private Limited is an AMFI-registered mutual fund distributor. Past performance does not guarantee future returns.",
    "tax": "I can share general information, but this is not personalized tax advice. Please consult a chartered accountant for your specific situation.",
}

TRUST_FACTS = {
    "company_identity": "Stable Money is operated by Stable-Alpha Technologies Pvt. Ltd.",
    "support_identity": "Stable Assist is Stable Money support for first-line voice help.",
    "partner_bank_model": "FDs are held directly with the RBI-regulated partner bank.",
    "dicgc": "Eligible bank deposits are insured up to 5 lakh rupees per depositor per bank under DICGC.",
    "tone_rule": "Answer trust questions short, fact-based, and without hype.",
}

SUPPORT_CONTACT = {
    "human_support_hours": "10:00-19:00 IST, Monday to Saturday",
    "contact_reference": "stablemoney.in/contact-us",
    "after_hours_wording": "Our human support team is available from 10 AM to 7 PM IST, Monday to Saturday. I can create a ticket for follow-up.",
    "grievance_sla": CANONICAL_SLAS["grievance_response"],
}

DEMO_FD_RATES = [
    {"issuer": "Shriram Finance", "tenure": "12 months", "regular_rate": "7.75% p.a.", "senior_citizen_rate": "8.25% p.a."},
    {"issuer": "Mahindra Finance", "tenure": "12 months", "regular_rate": "7.70% p.a.", "senior_citizen_rate": "8.20% p.a."},
    {"issuer": "Bajaj Finance", "tenure": "24 months", "regular_rate": "8.05% p.a.", "senior_citizen_rate": "8.55% p.a."},
]

STABLE_INTENT_POLICIES: dict[str, dict[str, Any]] = {
    "payment.failed": {"authTier": "Tier B", "tools": ["verify_read_access", "get_payment_reconciliation_status"]},
    "fd.book.status": {"authTier": "Tier B", "tools": ["verify_read_access", "get_fd_booking_status"]},
    "fd.withdraw.premature": {"authTier": "Tier C", "tools": ["verify_read_access", "get_premature_withdrawal_quote", "send_secure_link"]},
    "kyc.status": {"authTier": "Tier B", "tools": ["verify_read_access", "get_kyc_status"]},
    "kyc.explainer": {"authTier": "Tier A", "tools": []},
    "fd.rates.compare": {"authTier": "Tier A", "tools": ["get_fd_rates"]},
    "maturity.payout.delay": {"authTier": "Tier B", "tools": ["verify_read_access", "get_fd_booking_status"]},
    "app.real.check": {"authTier": "Tier A", "tools": ["get_trust_facts", "get_disclosure_copy"]},
    "ticket.status": {"authTier": "Tier B", "tools": ["verify_read_access", "get_support_ticket_status"]},
    "grievance.escalate": {"authTier": "Tier A/B", "tools": ["create_support_ticket", "get_support_contact"]},
    "support.contact": {"authTier": "Tier A", "tools": ["get_support_contact"]},
    "payment.summary": {"authTier": "Tier B", "tools": ["verify_read_access", "get_payment_summary"]},
    "fd.summary": {"authTier": "Tier B", "tools": ["verify_read_access", "get_fd_summary"]},
    "account.overview": {"authTier": "Tier A", "tools": ["get_account_overview"]},
    "refund.status": {"authTier": "Tier B", "tools": ["verify_read_access", "get_refund_status"]},
    "secure.action.help": {"authTier": "Tier C", "tools": ["send_secure_link", "create_support_ticket"]},
    "conversation.goodbye": {"authTier": "Tier A", "tools": []},
}

DETERMINISTIC_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("payment.failed", [
        "payment failed", "payment fail", "payment debit", "money debited", "fd nahi bana", "paisa atak", "paise cut",
        "पेमेंट फेल", "पैसा कट", "ਪੇਮੈਂਟ ਫੇਲ", "ਪੈਸੇ ਕੱਟ", "پیمنٹ فیل", "پیسے کٹ", "پیمینٹ فیل",
        "পেমেন্ট ফেল", "பேமெண்ட் ஃபெயில்", "పేమెంట్ ఫెయిల్", "પેમેન્ટ ફેલ",
        "பணம் கழிந்தது", "எஃப்டி உருவாகவில்லை", "ಹಣ ಕಡಿತವಾಗಿದೆ", "ಎಫ್ಡಿ ಆಗಿಲ್ಲ", "പണം പോയി", "എഫ്ഡി ആയില്ല",
    ]),
    ("fd.book.status", [
        "fd booking status", "fd booking", "fd booked", "fd bana", "fixed desposit status", "fixed deposit status",
        "मेरी एफडी बुक", "एफडी बुक", "एफडी बुकिंग", "ਐਫਡੀ ਬੁਕਿੰਗ", "ਐਫਡੀ ਸਟੇਟਸ",
        "ایف ڈی بکنگ", "ایف ڈی اسٹیٹس", "ایف ڈی سٹیٹس", "એફડી સ્ટેટસ", "एफडी बुक झाली",
        "এফডি বুক", "ಎಫ್ಡಿ ಬುಕ್", "എഫ്ഡി ബുക്ക്", "எஃப்டி புக்", "એફડી બુક",
    ]),
    ("fd.withdraw.premature", [
        "break my fd", "break fd", "close fd", "withdraw fd", "break my fixed deposit",
        "एफडी तोड़", "एफडी तोड़नी", "एफडी ब्रेक", "एफडी मोडायची", "ਐਫਡੀ ਤੋੜ", "ਐਫਡੀ ਤੋੜਨੀ",
        "ایف ڈی توڑ", "ایف ڈی توڑنی", "ایف ڈی کلوز", "এফডি ভাঙতে",
        "એફડી તોડવી", "ಎಫ್ಡಿ ಮುರಿಯ", "എഫ്ഡി പൊളിക്ക", "எஃப்டி உடைக்க", "ఎఫ్డి బ్రేక్",
    ]),
    ("kyc.explainer", [
        "what is kyc", "kyc kya hai", "kyc kya hota", "केवाईसी क्या है", "केवाईसी का मतलब", "केवायसी म्हणजे काय",
        "ਕੇਵਾਈਸੀ ਕੀ ਹੈ", "کے وائی سی کیا ہے", "کے وائی سی کیا ہوتا ہے", "કેવાયસી શું છે",
        "ಕೆವೈಸಿ ಎಂದರೆ ಏನು", "കെവൈസി എന്താണ്", "கேஒய்சி என்றால் என்ன", "কেওয়াইসি কী", "కేవైసీ అంటే ఏమిటి",
    ]),
    ("kyc.status", [
        "kyc status", "kyc pending", "kyc approve", "केवाईसी status", "केवाईसी का स्टेटस", "केवाईसी अप्रूव", "केवायसी स्थिती",
        "ਕੇਵਾਈਸੀ ਦਾ ਸਟੇਟਸ", "ਕੇਵਾਈਸੀ ਪੈਂਡਿੰਗ", "کے وائی سی کا سٹیٹس", "کے وائی سی سٹیٹس",
        "কেওয়াইসি স্টেটাস", "கேஒய்சி ஸ்டேட்டஸ்", "కేవైసీ స్టేటస్",
        "കെവൈസി സ്റ്റാറ്റസ്", "કેવાયસી સ્ટેટસ", "ಕೆವೈಸಿ ಸ್ಥಿತಿ", "কেওয়াইসি অবস্থা", "கேஒய்சி நிலை",
    ]),
    ("fd.rates.compare", [
        "fd rates", "fd rate", "fd interest rate", "fixed deposit rate", "interest rate",
        "एफडी रेट", "एफडी का ब्याज दर", "ਐਫਡੀ ਦਾ ਵਿਆਜ ਦਰ", "ایف ڈی کا انٹرسٹ ریٹ", "انٹرسٹ ریٹ", "எஃப்டி வட்டி ரேட்",
        "એફડી વ્યાજ દર", "ಎಫ್ಡಿ ಬಡ್ಡಿ ದರ", "എഫ്ഡി പലിശ നിരക്ക്", "এফডি সুদের হার", "ఎఫ్డి వడ్డీ రేటు",
    ]),
    ("maturity.payout.delay", [
        "maturity payout", "maturity amount", "मैच्योरिटी पेआउट", "मेच्योरिटी पेआउट", "ਮੈਚੋਰਿਟੀ ਪੇਆਉਟ",
        "میچورٹی پی آؤٹ", "مچورٹی پی آؤٹ", "મેચ્યોરિટી પેઆઉટ",
        "மெச்சூரிட்டி பணம்", "மெச்சூரிட்டி அமௌண்ட்", "ಮೆಚ್ಯುರಿಟಿ ಹಣ", "മെച്യൂരിറ്റി പണം", "ম্যাচুরিটি টাকা", "మెచ్యూరిటీ డబ్బు",
    ]),
    ("app.real.check", [
        "stable money real", "stable money safe", "dicgc", "partner bank", "स्टेबल मनी सेफ", "सेफ है",
        "ਸਟੇਬਲ ਮਨੀ ਸੇਫ", "سٹیبل منی سیف", "پارٹنر بینک", "স্টেবল মানি কি সেফ",
        "ಸ್ಟೇಬಲ್ ಮನಿ ಸುರಕ್ಷಿತ", "ಸ್ಟೇಬಲ್ ಮನಿ ಸುರಕ್ಷಿತವೇ", "ஸ்டேபிள் மணி பாதுகாப்பானதா", "സ്റ്റേബിൾ മണി സുരക്ഷിത", "સ્ટેબલ મની સુરક્ષિત", "స్టేబుల్ మనీ సురక్షిత",
    ]),
    ("ticket.status", [
        "ticket status", "टिकट का स्टेटस", "ਟਿਕਟ ਦਾ ਸਟੇਟਸ", "ٹکٹ کا سٹیٹس", "ٹکٹ سٹیٹس", "حالة التذكرة",
        "டிக்கெட் நிலை", "ಟಿಕೆಟ್ ಸ್ಥಿತಿ", "ടിക്കറ്റ് സ്റ്റാറ്റസ്", "টিকিট স্টেটাস", "ટિકિટ સ્ટેટસ", "టికెట్ స్థితి",
    ]),
    ("grievance.escalate", [
        "complaint", "complaint raise", "grievance", "escalate", "शिकायत दर्ज", "कम्प्लेंट", "ਸ਼ਿਕਾਇਤ ਦਰਜ", "شکایت درج", "کمپلینٹ",
        "অভিযোগ জানাতে", "ફરિયાદ નોંધ", "ದೂರು ದಾಖಲ", "പരാതി നൽക", "புகார் அளிக்க", "ఫిర్యాదు చేయ",
    ]),
    ("support.contact", [
        "support number", "support contact", "customer care", "support se baat", "madad chahiye",
        "सपोर्ट का नंबर", "ਸਪੋਰਟ ਨੰਬਰ", "سپورٹ نمبر", "સપોર્ટ નંબર", "সাপোর্ট নম্বর", "رقم الدعم",
        "કસ્ટમર કેર નંબર", "ಗ್ರಾಹಕ ಸೇವೆ ಸಂಖ್ಯೆ", "കസ്റ്റമർ കെയർ നമ്പർ", "கஸ்டமர் கேர் நம்பர்", "కస్టమర్ కేర్ నంబర్",
    ]),
    ("payment.summary", [
        "payment summary", "payment history", "mere payments", "my payments", "payments ke bare me", "payments ke bare mein",
        "mere pe ke bare", "mere pe ke baare", "mera payment", "mere payment", "payment ka status", "payment ke bare",
        "mere pe", "mera pe",
        "पेमेंट हिस्ट्री", "पेमेंट्स के बारे", "पेमेंट्स सांगा", "पेमेंट के बारे", "पेमेंट का स्टेटस",
        "मेरे पे", "मेरा पेमेंट", "मेरे पेमेंट", "पे के बारे में", "पे का स्टेटस",
        "ਪੇਮੈਂਟਸ ਬਾਰੇ", "ਪੇਮੈਂਟ ਬਾਰੇ", "میرے پے", "پیمنٹس کے بارے", "پیمنٹ کے بارے",
        "পেমেন্টস সম্পর্কে", "પેમેન્ટ્સ વિશે", "ಪೇಮೆಂಟ್ಸ್ ಬಗ್ಗೆ", "പേയ്‌മെന്റ്സ് കുറിച്ച്", "పేమెంట్ హిస్టరీ",
        "பேமெண்ட்ஸ் விவரம்", "ಪೇಮೆಂಟ್ ವಿವರ", "പേയ്‌മെന്റ് വിവരങ്ങൾ", "পেমেন্ট বিবরণ", "પેમેન્ટ વિગતો",
    ]),
    ("fd.summary", [
        "fd summary", "fd list", "fds list", "meri fd", "my fd", "fixed deposits", "fix deposit details",
        "एफडीज़ के बारे", "एफडी के बारे", "माझ्या एफडी", "ਐਫਡੀਜ਼ ਬਾਰੇ", "ਐਫਡੀ ਬਾਰੇ", "ایف ڈیز کے بارے", "ایف ڈی کے بارے", "ایف ڈی لسٹ",
        "এফডিগুলো সম্পর্কে", "એફડી લિસ્ટ", "એફડીઓ વિશે", "ಎಫ್ಡಿಗಳ ಬಗ್ಗೆ", "எஃப்டிகள் பற்றி",
        "ಎಫ್ಡಿ ಪಟ್ಟಿ", "എഫ്ഡി ലിസ്റ്റ്", "எஃப்டி லிஸ்ட்", "এফডি লিস্ট", "ఎఫ్డి లిస్ట్",
    ]),
    ("account.overview", [
        "account overview", "account status", "अकाउंट ओवरव्यू", "अकाउंट स्टेटस", "खाते स्थिती",
        "ਅਕਾਊਂਟ ਓਵਰਵਿਊ", "ਅਕਾਊਂਟ ਸਟੇਟਸ", "اکاؤنٹ اوورویو", "அக்கவுண்ட் ஸ்டேட்டஸ்",
        "એકાઉન્ટ સ્ટેટસ", "ಖಾತೆ ಸ್ಥಿತಿ", "അക്കൗണ്ട് സ്റ്റാറ്റസ്", "অ্যাকাউন্ট স্টেটাস", "అకౌంట్ స్టేటస్",
    ]),
    ("refund.status", [
        "refund status", "refund kab", "paisa wapas kab", "रिफंड कब", "ਰਿਫੰਡ ਕਦੋਂ", "ریفنڈ کب", "ریفنڈ سٹیٹس",
        "রিফান্ড স্টেটাস", "রিফান্ড কবে",
        "రిఫండ్ ఎప్పుడు", "રિફંડ ક્યારે", "ರಿಫಂಡ್ ಯಾವಾಗ", "റീഫണ്ട് എപ്പോൾ", "ரீஃபண்ட் எப்போது",
    ]),
    ("secure.action.help", [
        "mobile number change", "bank account change", "nominee update", "मोबाइल नंबर बदल", "मोबाइल नंबर बदलना", "मोबाइल चेंज", "बैंक अकाउंट बदल", "बैंक अकाउंट बदलना",
        "ਮੋਬਾਈਲ ਨੰਬਰ ਬਦਲ", "ਮੋਬਾਈਲ ਨੰਬਰ ਬਦਲਣਾ", "ਨੋਮਿਨੀ ਅਪਡੇਟ", "موبائل نمبر بدل", "موبائل نمبر بدلنا", "بینک چینج", "تغيير الجوال",
        "മൊബൈൽ നമ്പർ മാറ്റണം", "ಮೊಬೈಲ್ ನಂಬರ್ ಬದಲಾಯಿಸ", "மொபைல் நம்பர் மாற்ற", "મોબાઇલ નંબર બદલ", "మొబైల్ నంబర్ మార్చ",
    ]),
    ("conversation.goodbye", [
        "ok bye", "okay bye", "thanks bye", "thank you bye", "theek hai bye", "no thank you", "no thanks",
        "no thank u", "no thankyou", "nah thanks", "nahi thanks", "nahi thank you", "bas thanks", "bas ho gaya",
        "thats all", "that is all", "thanks that is all", "nothing else", "kuch aur nahi", "aur kuch nahi",
        "i am done", "im done", "i'm done", "main rakhta hoon", "ab main rakhta hoon", "call rakhta hoon",
        "नहीं धन्यवाद", "और कुछ नहीं", "कुछ और नहीं", "बस हो गया", "धन्यवाद बस", "कॉल रखता हूँ",
        "नको धन्यवाद", "अजून काही नाही", "बस झाले धन्यवाद", "कॉल ठेवतो",
        "ਨਹੀਂ ਧੰਨਵਾਦ", "ਹੋਰ ਕੁਝ ਨਹੀਂ", "ਬੱਸ ਹੋ ਗਿਆ", "ਕਾਲ ਰੱਖਦਾ ਹਾਂ",
        "نہیں شکریہ", "اور کچھ نہیں", "بس ہو گیا", "کال رکھتا ہوں",
        "আর কিছু না", "না ধন্যবাদ", "ধন্যবাদ আর কিছু নেই", "কল রাখছি",
        "ના આભાર", "બીજું કંઈ નહીં", "બસ થઈ ગયું", "કોલ રાખું છું",
        "ಬೇಡ ಧನ್ಯವಾದ", "ಇನ್ನೇನೂ ಇಲ್ಲ", "ಇಷ್ಟೇ ಸಾಕು", "ಕಾಲ್ ಇಡುತ್ತೇನೆ",
        "വേണ്ട നന്ദി", "മറ്റൊന്നുമില്ല", "ഇത്ര മതി", "കാൾ വെക്കുന്നു",
        "வேண்டாம் நன்றி", "வேற ஒன்றும் இல்லை", "இவ்வளவுதான்", "கால் வைக்கிறேன்",
        "వద్దు ధన్యవాదాలు", "ఇంకేమీ లేదు", "ఇంతే చాలు", "కాల్ పెట్టేస్తాను",
        "thank you call end", "call end", "goodbye", "bye", "theek hai thanks", "अलविदा", "धन्यवाद कॉल बंद", "बस इतना ही कॉल बंद",
        "ਧੰਨਵਾਦ ਕਾਲ ਬੰਦ", "شکریہ کال بند", "شکریہ", "بس اتنا ہی کال بند",
    ]),
]

KEYWORDS = DETERMINISTIC_INTENT_KEYWORDS


def route_for_intent(intent: str) -> dict[str, Any]:
    policy = STABLE_INTENT_POLICIES.get(intent)
    if not policy:
        return {"intent": "unknown", "authTier": "Tier A", "tools": []}
    return {"intent": intent, "authTier": policy["authTier"], "tools": list(policy["tools"])}


def get_stable_intent_policy(intent: str) -> dict[str, Any]:
    route = route_for_intent(intent)
    return {"authTier": route["authTier"], "tools": route["tools"]}


def normalize_transcript(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    chars: list[str] = []
    for char in normalized:
        category = unicodedata.category(char)
        chars.append(char if category[0] in {"L", "M", "N"} else " ")
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def _phrase_matches(normalized: str, pattern: str) -> bool:
    return f" {pattern} " in f" {normalized} "


def _is_short_contextual_turn(normalized: str) -> bool:
    if not normalized:
        return False
    if re.fullmatch(r"\d{2,6}", normalized):
        return True
    return len(normalized.split()) <= 4 and re.match(
        r"^(yes|haan|ha|ok|okay|dob|date|august|january|february|march|april|may|june|july|september|october|november|december|\d)",
        normalized,
    ) is not None


def trace_stable_turn_route(transcript: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    normalized = normalize_transcript(transcript)
    for intent, keywords in KEYWORDS:
        for keyword in keywords:
            pattern = normalize_transcript(keyword)
            if _phrase_matches(normalized, pattern):
                return {
                    "route": route_for_intent(intent),
                    "normalizedTranscript": normalized,
                    "matchSource": "keyword",
                    "matchedPattern": pattern,
                    "previousIntent": None,
                }
    if _is_short_contextual_turn(normalized):
        for item in reversed(history or []):
            if item.get("role") != "user":
                continue
            route = route_stable_turn(item.get("text", ""), [])
            if route["intent"] != "unknown":
                return {
                    "route": route,
                    "normalizedTranscript": normalized,
                    "matchSource": "history",
                    "matchedPattern": None,
                    "previousIntent": route["intent"],
                }
    return {
        "route": route_for_intent("unknown"),
        "normalizedTranscript": normalized,
        "matchSource": "unknown",
        "matchedPattern": None,
        "previousIntent": None,
    }


def route_stable_turn(transcript: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return trace_stable_turn_route(transcript, history)["route"]


def get_persona_suggestions(persona: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    def add(item_id: str, label: str, prompt: str, intent: str) -> None:
        policy = get_stable_intent_policy(intent)
        suggestions.append({"id": item_id, "label": label, "prompt": prompt, "intent": intent, "tools": policy["tools"]})

    payments = persona.get("payments") or []
    fds = persona.get("fixed_deposits") or []
    links = persona.get("secure_links") or []
    tickets = persona.get("open_tickets") or []
    if payments:
        add("payment-status", "Payment status", f"Check my payment {payments[0]['payment_reference']} and tell me what happens next.", "payment.failed")
    if fds:
        add("fd-booking-status", "FD status", f"Tell me the current status of {fds[0]['fd_id']} and any expected timeline.", "fd.book.status")
    add("kyc-status", "KYC update", "Check my KYC status and explain the next step clearly.", "kyc.status")
    premature = next((fd for fd in fds if fd.get("premature_withdrawal_estimate") is not None), None)
    if premature:
        add("premature-withdrawal", "Premature withdrawal", f"Explain premature withdrawal for {premature['fd_id']}, including estimate and penalty.", "fd.withdraw.premature")
    ready_link = next((link for link in links if link.get("status") == "ready_to_send"), None)
    if ready_link:
        add("secure-link", "Secure link", f"Send me the secure link for {ready_link['action'].replace('_', ' ')} on {ready_link.get('fd_id')}.", "secure.action.help")
    if tickets:
        add("ticket-status", "Ticket status", f"Check my ticket {tickets[0]['ticket_id']} and tell me the SLA.", "ticket.status")
    else:
        add("grievance", "Raise grievance", "Create a support follow-up ticket if my issue cannot be resolved on this call.", "grievance.escalate")
    return suggestions
