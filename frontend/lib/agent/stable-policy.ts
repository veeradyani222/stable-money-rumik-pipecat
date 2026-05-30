export const CANONICAL_SLAS = {
  fd_booking_processing: 'usually within 24 to 48 working hours',
  payment_reconciliation: 'booking may complete, otherwise refund usually reflects within 5 working days',
  maturity_payout: 'usually within 1 to 3 working days',
  grievance_response: 'within 48 hours',
  kyc_pending_review: 'usually within 24 working hours',
} as const;

export const DISCLOSURE_COPY = {
  recording: 'This call may be recorded for quality purposes.',
  fd: 'Stable Money is a distributor. FDs are held directly with the RBI-regulated partner bank and are insured up to 5 lakh rupees per depositor per bank under DICGC. FDs are not regulated by SEBI and are outside the SCORES and Exchange Arbitration framework.',
  mutual_fund:
    'Mutual fund investments are subject to market risks. Please read all scheme related documents carefully. Stable Finserv Private Limited is an AMFI-registered mutual fund distributor. Past performance does not guarantee future returns.',
  tax: 'I can share general information, but this is not personalized tax advice. Please consult a chartered accountant for your specific situation.',
} as const;

export const PROJECT_EXACT_LINES = {
  moneyAnxiety: 'I understand why that is worrying. Let me check the exact status for you.',
  rateCompare: "I can help compare rates, but I can't recommend one specific FD.",
  toolFailure:
    "I don't want to guess here. I couldn't fetch the latest detail right now. I can create a ticket or give you the support contact.",
  audioRepair: 'Sorry, the audio was not clear. Could you please repeat that once?',
  silenceFiveSeconds: 'Are you still there?',
  silenceTenSeconds: 'If this is not a good time, I can end the call and you can call again later.',
  outOfScope: 'That specific request is outside what I can complete on voice. I can either create a ticket or guide you to the right team.',
  afterHours:
    'Our human support team is available from 10 AM to 7 PM IST, Monday to Saturday. I can create a ticket for follow-up.',
  paymentSafe: 'aapka paisa safe hai',
  paymentWorstCase: 'worst case mein refund mil jayega, koi loss nahi hoga',
} as const;

export const TRUST_FACTS = {
  company_identity: 'Stable Money is operated by Stable-Alpha Technologies Pvt. Ltd.',
  support_identity: 'Stable Assist is Stable Money support for first-line voice help.',
  partner_bank_model: 'FDs are held directly with the RBI-regulated partner bank.',
  dicgc: 'Eligible bank deposits are insured up to 5 lakh rupees per depositor per bank under DICGC.',
  tone_rule: 'Answer trust questions short, fact-based, and without hype.',
} as const;

export const SUPPORT_CONTACT = {
  human_support_hours: '10:00-19:00 IST, Monday to Saturday',
  contact_reference: 'stablemoney.in/contact-us',
  after_hours_wording: PROJECT_EXACT_LINES.afterHours,
  grievance_sla: CANONICAL_SLAS.grievance_response,
} as const;

export const DEMO_FD_RATES = [
  {
    issuer: 'Shriram Finance',
    tenure: '12 months',
    regular_rate: '7.75% p.a.',
    senior_citizen_rate: '8.25% p.a.',
  },
  {
    issuer: 'Mahindra Finance',
    tenure: '12 months',
    regular_rate: '7.70% p.a.',
    senior_citizen_rate: '8.20% p.a.',
  },
  {
    issuer: 'Bajaj Finance',
    tenure: '24 months',
    regular_rate: '8.05% p.a.',
    senior_citizen_rate: '8.55% p.a.',
  },
] as const;

export type StableAuthTier = 'Tier A' | 'Tier B' | 'Tier C' | 'Tier A/B';

export type StableIntentId =
  | 'payment.failed'
  | 'fd.book.status'
  | 'fd.withdraw.premature'
  | 'kyc.status'
  | 'kyc.explainer'
  | 'fd.rates.compare'
  | 'maturity.payout.delay'
  | 'app.real.check'
  | 'ticket.status'
  | 'grievance.escalate'
  | 'support.contact'
  | 'payment.summary'
  | 'fd.summary'
  | 'account.overview'
  | 'refund.status'
  | 'secure.action.help'
  | 'conversation.goodbye'
  | 'unknown';

export interface StableIntentPolicy {
  authTier: StableAuthTier;
  tools: string[];
}

export interface StableIntentRoute extends StableIntentPolicy {
  intent: StableIntentId;
}

export interface StableTurnHistoryMessage {
  role: 'user' | 'model';
  text: string;
}

export const STABLE_INTENT_POLICIES: Record<Exclude<StableIntentId, 'unknown'>, StableIntentPolicy> = {
  'payment.failed': {
    authTier: 'Tier B',
    tools: ['verify_read_access', 'get_payment_reconciliation_status'],
  },
  'fd.book.status': {
    authTier: 'Tier B',
    tools: ['verify_read_access', 'get_fd_booking_status'],
  },
  'fd.withdraw.premature': {
    authTier: 'Tier C',
    tools: ['verify_read_access', 'get_premature_withdrawal_quote', 'send_secure_link'],
  },
  'kyc.status': {
    authTier: 'Tier B',
    tools: ['verify_read_access', 'get_kyc_status'],
  },
  'kyc.explainer': {
    authTier: 'Tier A',
    tools: [],
  },
  'fd.rates.compare': {
    authTier: 'Tier A',
    tools: ['get_fd_rates'],
  },
  'maturity.payout.delay': {
    authTier: 'Tier B',
    tools: ['verify_read_access', 'get_fd_booking_status'],
  },
  'app.real.check': {
    authTier: 'Tier A',
    tools: ['get_trust_facts', 'get_disclosure_copy'],
  },
  'ticket.status': {
    authTier: 'Tier B',
    tools: ['verify_read_access', 'get_support_ticket_status'],
  },
  'grievance.escalate': {
    authTier: 'Tier A/B',
    tools: ['create_support_ticket', 'get_support_contact'],
  },
  'support.contact': {
    authTier: 'Tier A',
    tools: ['get_support_contact'],
  },
  'payment.summary': {
    authTier: 'Tier B',
    tools: ['verify_read_access', 'get_payment_summary'],
  },
  'fd.summary': {
    authTier: 'Tier B',
    tools: ['verify_read_access', 'get_fd_summary'],
  },
  'account.overview': {
    authTier: 'Tier A',
    tools: ['get_account_overview'],
  },
  'refund.status': {
    authTier: 'Tier B',
    tools: ['verify_read_access', 'get_refund_status'],
  },
  'secure.action.help': {
    authTier: 'Tier C',
    tools: ['send_secure_link', 'create_support_ticket'],
  },
  'conversation.goodbye': {
    authTier: 'Tier A',
    tools: [],
  },
} as const;

export function getStableIntentPolicy(intent: Exclude<StableIntentId, 'unknown'>): StableIntentPolicy {
  const policy = STABLE_INTENT_POLICIES[intent];
  return {
    authTier: policy.authTier,
    tools: [...policy.tools],
  };
}

function unknownIntentRoute(): StableIntentRoute {
  return {
    intent: 'unknown',
    authTier: 'Tier A',
    tools: [],
  };
}

type DeterministicIntentKeywordRow = {
  intent: Exclude<StableIntentId, 'unknown'>;
  keywords: string[];
};

export interface StableTurnRouteTrace {
  route: StableIntentRoute;
  normalizedTranscript: string;
  matchSource: 'keyword' | 'history' | 'unknown';
  matchedPattern: string | null;
  previousIntent: StableIntentId | null;
}

export const DETERMINISTIC_INTENT_KEYWORDS: DeterministicIntentKeywordRow[] = [
  {
    intent: 'payment.failed',
    keywords: [
      'payment failed', 'payment fail', 'payment debit', 'money debited', 'fd nahi bana', 'paisa atak', 'paise cut',
      'पेमेंट फेल', 'पैसा कट', 'ਪੇਮੈਂਟ ਫੇਲ', 'ਪੈਸੇ ਕੱਟ', 'پیمنٹ فیل', 'پیسے کٹ', 'پیمینٹ فیل',
      'পেমেন্ট ফেল', 'பேமெண்ட் ஃபெயில்', 'పేమెంట్ ఫెయిల్', 'પેમેન્ટ ફેલ',
      'பணம் கழிந்தது', 'எஃப்டி உருவாகவில்லை', 'ಹಣ ಕಡಿತವಾಗಿದೆ', 'ಎಫ್ಡಿ ಆಗಿಲ್ಲ', 'പണം പോയി', 'എഫ്ഡി ആയില്ല',
    ],
  },
  {
    intent: 'fd.book.status',
    keywords: [
      'fd booking status', 'fd booking', 'fd booked', 'fd bana', 'fixed desposit status', 'fixed deposit status',
      'मेरी एफडी बुक', 'एफडी बुक', 'एफडी बुकिंग', 'ਐਫਡੀ ਬੁਕਿੰਗ', 'ਐਫਡੀ ਸਟੇਟਸ',
      'ایف ڈی بکنگ', 'ایف ڈی اسٹیٹس', 'ایف ڈی سٹیٹس', 'એફડી સ્ટેટસ', 'एफडी बुक झाली',
      'এফডি বুক', 'ಎಫ್ಡಿ ಬುಕ್', 'എഫ്ഡി ബുക്ക്', 'எஃப்டி புக்', 'એફડી બુક',
    ],
  },
  {
    intent: 'fd.withdraw.premature',
    keywords: [
      'break my fd', 'break fd', 'close fd', 'withdraw fd', 'break my fixed deposit',
      'एफडी तोड़', 'एफडी तोड़नी', 'एफडी ब्रेक', 'एफडी मोडायची', 'ਐਫਡੀ ਤੋੜ', 'ਐਫਡੀ ਤੋੜਨੀ', 'ایف ڈی توڑ', 'ایف ڈی توڑنی', 'ایف ڈی کلوز', 'এফডি ভাঙতে',
      'એફડી તોડવી', 'ಎಫ್ಡಿ ಮುರಿಯ', 'എഫ്ഡി പൊളിക്ക', 'எஃப்டி உடைக்க', 'ఎఫ్డి బ్రేక్',
    ],
  },
  {
    intent: 'kyc.explainer',
    keywords: [
      'what is kyc', 'kyc kya hai', 'kyc kya hota', 'केवाईसी क्या है', 'केवाईसी का मतलब', 'केवायसी म्हणजे काय',
      'ਕੇਵਾਈਸੀ ਕੀ ਹੈ', 'کے وائی سی کیا ہے', 'کے وائی سی کیا ہوتا ہے', 'કેવાયસી શું છે',
      'ಕೆವೈಸಿ ಎಂದರೆ ಏನು', 'കെവൈസി എന്താണ്', 'கேஒய்சி என்றால் என்ன', 'কেওয়াইসি কী', 'కేవైసీ అంటే ఏమిటి',
    ],
  },
  {
    intent: 'kyc.status',
    keywords: [
      'kyc status', 'kyc pending', 'kyc approve', 'केवाईसी status', 'केवाईसी का स्टेटस', 'केवाईसी अप्रूव', 'केवायसी स्थिती',
      'ਕੇਵਾਈਸੀ ਦਾ ਸਟੇਟਸ', 'ਕੇਵਾਈਸੀ ਪੈਂਡਿੰਗ', 'کے وائی سی کا سٹیٹس', 'کے وائی سی سٹیٹس',
      'কেওয়াইসি স্টেটাস', 'கேஒய்சி ஸ்டேட்டஸ்', 'కేవైసీ స్టేటస్',
      'കെവൈസി സ്റ്റാറ്റസ്', 'કેવાયસી સ્ટેટસ', 'ಕೆವೈಸಿ ಸ್ಥಿತಿ', 'কেওয়াইসি অবস্থা', 'கேஒய்சி நிலை',
    ],
  },
  {
    intent: 'fd.rates.compare',
    keywords: [
      'fd rates', 'fd rate', 'fd interest rate', 'fixed deposit rate', 'interest rate',
      'एफडी रेट', 'एफडी का ब्याज दर', 'ਐਫਡੀ ਦਾ ਵਿਆਜ ਦਰ', 'ایف ڈی کا انٹرسٹ ریٹ', 'انٹرسٹ ریٹ', 'எஃப்டி வட்டி ரேட்',
      'એફડી વ્યાજ દર', 'ಎಫ್ಡಿ ಬಡ್ಡಿ ದರ', 'എഫ്ഡി പലിശ നിരക്ക്', 'এফডি সুদের হার', 'ఎఫ్డి వడ్డీ రేటు',
    ],
  },
  {
    intent: 'maturity.payout.delay',
    keywords: [
      'maturity payout', 'maturity amount', 'मैच्योरिटी पेआउट', 'मेच्योरिटी पेआउट', 'ਮੈਚੋਰਿਟੀ ਪੇਆਉਟ',
      'میچورٹی پی آؤٹ', 'مچورٹی پی آؤٹ', 'મેચ્યોરિટી પેઆઉટ',
      'மெச்சூரிட்டி பணம்', 'மெச்சூரிட்டி அமௌண்ட்', 'ಮೆಚ್ಯುರಿಟಿ ಹಣ', 'മെച്യൂരിറ്റി പണം', 'ম্যাচুরিটি টাকা', 'మెచ్యూరిటీ డబ్బు',
    ],
  },
  {
    intent: 'app.real.check',
    keywords: [
      'stable money real', 'stable money safe', 'dicgc', 'partner bank', 'स्टेबल मनी सेफ', 'सेफ है',
      'ਸਟੇਬਲ ਮਨੀ ਸੇਫ', 'سٹیبل منی سیف', 'پارٹنر بینک', 'স্টেবল মানি কি সেফ',
      'ಸ್ಟೇಬಲ್ ಮನಿ ಸುರಕ್ಷಿತ', 'ಸ್ಟೇಬಲ್ ಮನಿ ಸುರಕ್ಷಿತವೇ', 'ஸ்டேபிள் மணி பாதுகாப்பானதா', 'സ്റ്റേബിൾ മണി സുരക്ഷിത', 'સ્ટેબલ મની સુરક્ષિત', 'స్టేబుల్ మనీ సురక్షిత',
    ],
  },
  {
    intent: 'ticket.status',
    keywords: [
      'ticket status', 'टिकट का स्टेटस', 'ਟਿਕਟ ਦਾ ਸਟੇਟਸ', 'ٹکٹ کا سٹیٹس', 'ٹکٹ سٹیٹس', 'حالة التذكرة',
      'டிக்கெட் நிலை', 'ಟಿಕೆಟ್ ಸ್ಥಿತಿ', 'ടിക്കറ്റ് സ്റ്റാറ്റസ്', 'টিকিট স্টেটাস', 'ટિકિટ સ્ટેટસ', 'టికెట్ స్థితి',
    ],
  },
  {
    intent: 'grievance.escalate',
    keywords: [
      'complaint', 'complaint raise', 'grievance', 'escalate', 'शिकायत दर्ज', 'कम्प्लेंट', 'ਸ਼ਿਕਾਇਤ ਦਰਜ', 'شکایت درج', 'کمپلینٹ',
      'অভিযোগ জানাতে', 'ફરિયાદ નોંધ', 'ದೂರು ದಾಖಲ', 'പരാതി നൽക', 'புகார் அளிக்க', 'ఫిర్యాదు చేయ',
    ],
  },
  {
    intent: 'support.contact',
    keywords: [
      'support number', 'support contact', 'customer care', 'support se baat', 'madad chahiye',
      'सपोर्ट का नंबर', 'ਸਪੋਰਟ ਨੰਬਰ', 'سپورٹ نمبر', 'સપોર્ટ નંબર', 'সাপোর্ট নম্বর', 'رقم الدعم',
      'કસ્ટમર કેર નંબર', 'ಗ್ರಾಹಕ ಸೇವೆ ಸಂಖ್ಯೆ', 'കസ്റ്റമർ കെയർ നമ്പർ', 'கஸ்டமர் கேர் நம்பர்', 'కస్టమర్ కేర్ నంబర్',
    ],
  },
  {
    intent: 'payment.summary',
    keywords: [
      'payment summary', 'payment history', 'mere payments', 'my payments', 'payments ke bare me', 'payments ke bare mein',
      'mere pe ke bare', 'mere pe ke baare', 'mera payment', 'mere payment', 'payment ka status', 'payment ke bare',
      'mere pe', 'mera pe',
      'पेमेंट हिस्ट्री', 'पेमेंट्स के बारे', 'पेमेंट्स सांगा', 'पेमेंट के बारे', 'पेमेंट का स्टेटस',
      'मेरे पे', 'मेरा पेमेंट', 'मेरे पेमेंट', 'पे के बारे में', 'पे का स्टेटस',
      'ਪੇਮੈਂਟਸ ਬਾਰੇ', 'ਪੇਮੈਂਟ ਬਾਰੇ', 'میرے پے', 'پیمنٹس کے بارے', 'پیمنٹ کے بارے',
      'পেমেন্টস সম্পর্কে', 'પેમેન્ટ્સ વિશે', 'ಪೇಮೆಂಟ್ಸ್ ಬಗ್ಗೆ', 'പേയ്‌മെന്റ്സ് കുറിച്ച്', 'పేమెంట్ హిస్టరీ',
      'பேமெண்ட்ஸ் விவரம்', 'ಪೇಮೆಂಟ್ ವಿವರ', 'പേയ്‌മെന്റ് വിവരങ്ങൾ', 'পেমেন্ট বিবরণ', 'પેમેન્ટ વિગતો',
    ],
  },
  {
    intent: 'fd.summary',
    keywords: [
      'fd summary', 'fd list', 'fds list', 'meri fd', 'my fd', 'fixed deposits', 'fix deposit details',
      'एफडीज़ के बारे', 'एफडी के बारे', 'माझ्या एफडी', 'ਐਫਡੀਜ਼ ਬਾਰੇ', 'ਐਫਡੀ ਬਾਰੇ', 'ایف ڈیز کے بارے', 'ایف ڈی کے بارے', 'ایف ڈی لسٹ',
      'এফডিগুলো সম্পর্কে', 'એફડી લિસ્ટ', 'એફડીઓ વિશે', 'ಎಫ್ಡಿಗಳ ಬಗ್ಗೆ', 'எஃப்டிகள் பற்றி',
      'ಎಫ್ಡಿ ಪಟ್ಟಿ', 'എഫ്ഡി ലിസ്റ്റ്', 'எஃப்டி லிஸ்ட்', 'এফডি লিস্ট', 'ఎఫ్డి లిస్ట్',
    ],
  },
  {
    intent: 'account.overview',
    keywords: [
      'account overview', 'account status', 'अकाउंट ओवरव्यू', 'अकाउंट स्टेटस', 'खाते स्थिती',
      'ਅਕਾਊਂਟ ਓਵਰਵਿਊ', 'ਅਕਾਊਂਟ ਸਟੇਟਸ', 'اکاؤنٹ اوورویو', 'அக்கவுண்ட் ஸ்டேட்டஸ்',
      'એકાઉન્ટ સ્ટેટસ', 'ಖಾತೆ ಸ್ಥಿತಿ', 'അക്കൗണ്ട് സ്റ്റാറ്റസ്', 'অ্যাকাউন্ট স্টেটাস', 'అకౌంట్ స్టేటస్',
    ],
  },
  {
    intent: 'refund.status',
    keywords: [
      'refund status', 'refund kab', 'paisa wapas kab', 'रिफंड कब', 'ਰਿਫੰਡ ਕਦੋਂ', 'ریفنڈ کب', 'ریفنڈ سٹیٹس',
      'রিফান্ড স্টেটাস', 'রিফান্ড কবে',
      'రిఫండ్ ఎప్పుడు', 'રિફંડ ક્યારે', 'ರಿಫಂಡ್ ಯಾವಾಗ', 'റീഫണ്ട് എപ്പോൾ', 'ரீஃபண்ட் எப்போது',
    ],
  },
  {
    intent: 'secure.action.help',
    keywords: [
      'mobile number change', 'bank account change', 'nominee update', 'मोबाइल नंबर बदल', 'मोबाइल नंबर बदलना', 'मोबाइल चेंज', 'बैंक अकाउंट बदल', 'बैंक अकाउंट बदलना',
      'ਮੋਬਾਈਲ ਨੰਬਰ ਬਦਲ', 'ਮੋਬਾਈਲ ਨੰਬਰ ਬਦਲਣਾ', 'ਨੋਮਿਨੀ ਅਪਡੇਟ', 'موبائل نمبر بدل', 'موبائل نمبر بدلنا', 'بینک چینج', 'تغيير الجوال',
      'മൊബൈൽ നമ്പർ മാറ്റണം', 'ಮೊಬೈಲ್ ನಂಬರ್ ಬದಲಾಯಿಸ', 'மொபைல் நம்பர் மாற்ற', 'મોબાઇલ નંબર બદલ', 'మొబైల్ నంబర్ మార్చ',
    ],
  },
  {
    intent: 'conversation.goodbye',
    keywords: [
      'ok bye', 'okay bye', 'thanks bye', 'thank you bye', 'theek hai bye', 'no thank you', 'no thanks',
      'no thank u', 'no thankyou', 'nah thanks', 'nahi thanks', 'nahi thank you', 'bas thanks', 'bas ho gaya',
      'thats all', 'that is all', 'thanks that is all', 'nothing else', 'kuch aur nahi', 'aur kuch nahi',
      'i am done', 'im done', "i'm done", 'main rakhta hoon', 'ab main rakhta hoon', 'call rakhta hoon',
      'नहीं धन्यवाद', 'और कुछ नहीं', 'कुछ और नहीं', 'बस हो गया', 'धन्यवाद बस', 'कॉल रखता हूँ',
      'नको धन्यवाद', 'अजून काही नाही', 'बस झाले धन्यवाद', 'कॉल ठेवतो',
      'ਨਹੀਂ ਧੰਨਵਾਦ', 'ਹੋਰ ਕੁਝ ਨਹੀਂ', 'ਬੱਸ ਹੋ ਗਿਆ', 'ਕਾਲ ਰੱਖਦਾ ਹਾਂ',
      'نہیں شکریہ', 'اور کچھ نہیں', 'بس ہو گیا', 'کال رکھتا ہوں',
      'আর কিছু না', 'না ধন্যবাদ', 'ধন্যবাদ আর কিছু নেই', 'কল রাখছি',
      'ના આભાર', 'બીજું કંઈ નહીં', 'બસ થઈ ગયું', 'કોલ રાખું છું',
      'ಬೇಡ ಧನ್ಯವಾದ', 'ಇನ್ನೇನೂ ಇಲ್ಲ', 'ಇಷ್ಟೇ ಸಾಕು', 'ಕಾಲ್ ಇಡುತ್ತೇನೆ',
      'വേണ്ട നന്ദി', 'മറ്റൊന്നുമില്ല', 'ഇത്ര മതി', 'കാൾ വെക്കുന്നു',
      'வேண்டாம் நன்றி', 'வேற ஒன்றும் இல்லை', 'இவ்வளவுதான்', 'கால் வைக்கிறேன்',
      'వద్దు ధన్యవాదాలు', 'ఇంకేమీ లేదు', 'ఇంతే చాలు', 'కాల్ పెట్టేస్తాను',
      'thank you call end', 'call end', 'goodbye', 'bye', 'theek hai thanks', 'अलविदा', 'धन्यवाद कॉल बंद', 'बस इतना ही कॉल बंद',
      'ਧੰਨਵਾਦ ਕਾਲ ਬੰਦ', 'شکریہ کال بند', 'شکریہ', 'بس اتنا ہی کال بند',
    ],
  },
];

function routeFromStableIntent(intent: Exclude<StableIntentId, 'unknown'>): StableIntentRoute {
  return { intent, ...getStableIntentPolicy(intent) };
}

function normalizeStableTranscript(transcript: string): string {
  return transcript
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[^\p{L}\p{M}\p{N}]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function phraseMatches(normalizedTranscript: string, normalizedPattern: string): boolean {
  if (!normalizedTranscript || !normalizedPattern) return false;
  return ` ${normalizedTranscript} `.includes(` ${normalizedPattern} `);
}

function findKeywordRoute(normalizedTranscript: string): { route: StableIntentRoute; matchedPattern: string | null } {
  for (const row of DETERMINISTIC_INTENT_KEYWORDS) {
    for (const keyword of row.keywords) {
      const normalizedPattern = normalizeStableTranscript(keyword);
      if (phraseMatches(normalizedTranscript, normalizedPattern)) {
        return { route: routeFromStableIntent(row.intent), matchedPattern: normalizedPattern };
      }
    }
  }

  return { route: unknownIntentRoute(), matchedPattern: null };
}

function isShortContextualTurn(normalizedTranscript: string): boolean {
  if (!normalizedTranscript) return false;
  if (/^\d{2,6}$/.test(normalizedTranscript)) return true;
  const tokenCount = normalizedTranscript.split(' ').length;
  return tokenCount <= 4 && /^(yes|haan|ha|ok|okay|dob|date|august|january|february|march|april|may|june|july|september|october|november|december|\d)/.test(normalizedTranscript);
}

function previousKnownRoute(history: StableTurnHistoryMessage[]): StableIntentRoute | null {
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index].role !== 'user') continue;
    const route = routeStableIntent(history[index].text);
    if (route.intent !== 'unknown') return route;
  }
  return null;
}

export function traceStableTurnRoute(transcript: string, history: StableTurnHistoryMessage[] = []): StableTurnRouteTrace {
  const normalizedTranscript = normalizeStableTranscript(transcript);
  const keywordHit = findKeywordRoute(normalizedTranscript);
  if (keywordHit.route.intent !== 'unknown') {
    return {
      route: keywordHit.route,
      normalizedTranscript,
      matchSource: 'keyword',
      matchedPattern: keywordHit.matchedPattern,
      previousIntent: null,
    };
  }

  const previousRoute = isShortContextualTurn(normalizedTranscript) ? previousKnownRoute(history) : null;
  if (previousRoute) {
    return {
      route: previousRoute,
      normalizedTranscript,
      matchSource: 'history',
      matchedPattern: null,
      previousIntent: previousRoute.intent,
    };
  }

  return {
    route: unknownIntentRoute(),
    normalizedTranscript,
    matchSource: 'unknown',
    matchedPattern: null,
    previousIntent: null,
  };
}

export function routeStableIntent(transcript: string): StableIntentRoute {
  return traceStableTurnRoute(transcript).route;
}

export function routeStableTurn(transcript: string, history: StableTurnHistoryMessage[] = []): StableIntentRoute {
  return traceStableTurnRoute(transcript, history).route;
}
export function buildStableProjectPromptRules(route?: StableIntentRoute): string {
  const currentScenarioRules: Partial<Record<StableIntentId, string>> = {
    'payment.failed':
      'Current scenario: payment.failed. Reassure before policy, verify read access, call the allowed payment status tool, explain booking-or-refund, and offer escalation only when appropriate.',
    'fd.book.status':
      'Current scenario: fd.book.status. Verify read access, call the allowed FD booking status tool, and escalate only if failed or processing beyond the approved timeline.',
    'fd.withdraw.premature':
      'Current scenario: fd.withdraw.premature. Verify read access, explain estimate and penalty from the allowed quote tool, send a secure link when allowed, and do not execute withdrawal on voice.',
    'kyc.status':
      'Current scenario: kyc.status. Verify read access, call the allowed KYC status tool, and if rejected use only the backend reason.',
    'kyc.explainer':
      'Current scenario: kyc.explainer. Briefly explain that KYC means Know Your Customer identity verification, and say status checks need verification.',
    'fd.rates.compare':
      'Current scenario: fd.rates.compare. No account verification is needed, compare rates only, and do not say best FD.',
    'maturity.payout.delay':
      'Current scenario: maturity.payout.delay. Verify read access, call the allowed FD status tool, reassure before the approved payout timeline, and escalate only beyond the approved delay window.',
    'app.real.check':
      'Current scenario: app.real.check. Use approved trust facts and disclosure copy when allowed; keep it short and fact-based.',
    'ticket.status':
      'Current scenario: ticket.status. Verify read access, call the allowed ticket status tool, then summarize status and SLA.',
    'grievance.escalate':
      'Current scenario: grievance.escalate. Capture issue summary and priority, create the support ticket when issue context is available, and give the ticket ID before ending.',
    'support.contact':
      'Current scenario: support.contact. Share approved support contact and hours only.',
    'conversation.goodbye':
      'Current scenario: conversation.goodbye. Say goodbye briefly and nicely, mention that you are going to end the call now, do not use tools, and do not ask another question.',
  };
  const lines = [
    'Follow these exact scenario rules. Fixed auth tier routing is owned by code; do not override the current turn route.',
    '',
    'Auth rules:',
    '- Tier A needs no auth: rates, FAQs, trust checks, product explainers, support contact details.',
    '- Tier B needs verified read access: FD booking status, payment status, KYC status, payout schedule, ticket status.',
    '- Tier C is never completed on voice: change mobile, payout bank, premature withdrawal execution, payout changes, nominee/profile legal changes.',
    '- Do not ask the caller to read an OTP aloud on voice.',
    '- Never ask for full Aadhaar, CVV, PIN, bank password, or read back a full mobile number.',
    '',
    `Audio repair exact line: "${PROJECT_EXACT_LINES.audioRepair}"`,
    `Out-of-scope exact line: "${PROJECT_EXACT_LINES.outOfScope}"`,
    `After-hours exact line: "${PROJECT_EXACT_LINES.afterHours}"`,
    `FD disclosure exact copy: "${DISCLOSURE_COPY.fd}"`,
    `Tax disclaimer exact copy: "${DISCLOSURE_COPY.tax}"`,
  ];

  const scenarioRule = route ? currentScenarioRules[route.intent] : undefined;
  if (scenarioRule) {
    lines.push('', scenarioRule);
  }

  return lines.join('\n');
}
