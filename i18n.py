"""Hindi translations.

Keyed on the english string so templates stay readable - {{ t("Book a Slot") }}.
If a string is missing from the dict it just falls back to english, so a half
finished translation doesn't break the page.

Only the farmer side is translated. Centre staff use the english admin screens.
TODO: move this to flask-babel if we ever add a third language
"""

from flask import session

HINDI = {
    # site chrome
    "Krishi Sutra": "कृषि सूत्र",
    "Procurement Slot Booking Portal": "खरीद स्लॉट बुकिंग पोर्टल",
    "Slot Booking & Procurement Management System": "स्लॉट बुकिंग एवं खरीद प्रबंधन प्रणाली",
    "Government of India": "भारत सरकार",
    "Ministry of Consumer Affairs, Food & Public Distribution":
        "उपभोक्ता मामले, खाद्य एवं सार्वजनिक वितरण मंत्रालय",
    "Department of Consumer Affairs": "उपभोक्ता मामले विभाग",
    "Farmer sign in": "किसान लॉगिन",
    "Centre staff": "केंद्र कर्मचारी",
    "Sign out": "साइन आउट",
    "Skip to main content": "मुख्य सामग्री पर जाएं",
    "Display settings": "प्रदर्शन सेटिंग्स",
    "Smaller text": "छोटा अक्षर",
    "Normal text size": "सामान्य अक्षर आकार",
    "Larger text": "बड़ा अक्षर",

    # footer
    "Related links": "संबंधित लिंक",
    "Policies": "नीतियां",
    "Contact": "संपर्क",
    "About this portal": "इस पोर्टल के बारे में",
    "Kisan Call Centre (national)": "किसान कॉल सेंटर (राष्ट्रीय)",
    "District Supply Office": "जिला आपूर्ति कार्यालय",
    "Rudrapur, Udham Singh Nagar": "रुद्रपुर, उधम सिंह नगर",
    "Uttarakhand 263153": "उत्तराखंड 263153",
    "Problem statement": "समस्या विवरण",
    "Last updated on": "अंतिम अद्यतन",
    "Visitors": "आगंतुक",

    # weather lookup on the home page
    "Weather where you farm": "आपके क्षेत्र का मौसम",
    "Live forecast": "लाइव पूर्वानुमान",
    "Simulated forecast": "अनुमानित पूर्वानुमान",
    "Rain while your harvest waits at home is what gets it downgraded at the gate. "
    "Check the next five days before you pick a slot.":
        "घर पर रखी उपज पर बारिश ही उसे गेट पर कम ग्रेड दिलाती है। स्लॉट चुनने से पहले "
        "अगले पांच दिन का मौसम देख लें।",
    "Your district": "आपका जिला",
    "Select a district": "जिला चुनें",
    "Show forecast": "मौसम देखें",
    "humidity": "नमी",
    "Reading taken at": "यह जानकारी है",
    "That is the nearest station the weather service knows.":
        "मौसम विभाग को ज्ञात निकटतम केंद्र यही है।",
    "No forecast available for that district right now.":
        "इस जिले के लिए अभी कोई पूर्वानुमान उपलब्ध नहीं है।",

    # queue position on the booking page
    "Your place in the queue": "कतार में आपका स्थान",
    "You are number": "आप क्रमांक",
    "of": "में से",
    "booked in this time window": "इस समय स्लॉट में बुक हैं",
    "of those ahead of you have already been weighed in":
        "आपसे आगे वालों में से इतने की तौल हो चुकी है",
    "ahead of you have not arrived yet": "आपसे आगे वाले अभी नहीं पहुंचे हैं",
    "Nobody is ahead of you in this window": "इस स्लॉट में आपसे आगे कोई नहीं है",
    "is running about": "लगभग",
    "minutes behind": "मिनट पीछे चल रहा है",
    "centre last updated this": "केंद्र ने यह अंतिम बार बताया",
    "minutes ago": "मिनट पहले",
    "just now": "अभी-अभी",
    "hours ago": "घंटे पहले",
    "This is your position, not a promise about the clock. How long each farmer takes "
    "depends on the load being weighed and any quality check, so treat it as a guide.":
        "यह आपका क्रम है, समय का वादा नहीं। हर किसान में कितना समय लगेगा यह तौली जा रही "
        "उपज और गुणवत्ता जांच पर निर्भर करता है, इसलिए इसे अनुमान मानें।",
    "For centre staff": "केंद्र कर्मचारी हेतु",
    "Prototype for demonstration only. Aadhaar, bank and land-record details are mock data "
    "and are not verified against any live government database. Payment status is simulated.":
        "केवल प्रदर्शन हेतु प्रारूप। आधार, बैंक और भूमि रिकॉर्ड विवरण नमूना डेटा हैं और किसी भी "
        "सरकारी डेटाबेस से सत्यापित नहीं हैं। भुगतान की स्थिति अनुकरणीय है।",
    "Home": "होम",
    "Register": "पंजीकरण",
    "Farmer Sign In": "किसान लॉगिन",
    "Dashboard": "डैशबोर्ड",
    "Book a Slot": "स्लॉट बुक करें",
    "Payments": "भुगतान",
    "Alerts": "सूचनाएं",
    "My Details": "मेरी जानकारी",
    "English": "English",
    "हिन्दी": "हिन्दी",

    # home page
    "Book your procurement slot before you harvest":
        "कटाई से पहले अपना खरीद स्लॉट बुक करें",
    "Reserve a weighing slot at your nearest government procurement centre, verify your payment "
    "details in advance, and track your payment — without standing in a queue at the mandi gate.":
        "अपने निकटतम सरकारी खरीद केंद्र पर तौल का समय पहले से आरक्षित करें, अपने भुगतान की "
        "जानकारी पहले जांच लें, और भुगतान की स्थिति देखें — मंडी गेट पर कतार में लगे बिना।",
    "Procurement centres": "खरीद केंद्र",
    "Registered farmers": "पंजीकृत किसान",
    "Slots booked": "बुक किए गए स्लॉट",
    "Slots still open": "उपलब्ध स्लॉट",
    "For farmers": "किसानों के लिए",
    "For centre staff": "केंद्र कर्मचारियों के लिए",
    "Manage slot capacity, verify arriving produce, record quantity and quality grade, "
    "close transactions, and clear flagged farmer records before they hold up a payment.":
        "स्लॉट क्षमता प्रबंधित करें, आने वाली उपज की जांच करें, मात्रा और गुणवत्ता ग्रेड "
        "दर्ज करें, लेनदेन पूरा करें, और भुगतान रुकने से पहले चिह्नित किसान रिकॉर्ड ठीक करें।",
    "Register once with your mobile number. You can then book, reschedule or cancel a slot, "
    "and check your payment status at any time.":
        "अपने मोबाइल नंबर से एक बार पंजीकरण करें। इसके बाद आप कभी भी स्लॉट बुक, आगे-पीछे या "
        "रद्द कर सकते हैं, और भुगतान की स्थिति देख सकते हैं।",
    "Sign in": "लॉगिन",
    "No smartphone?": "स्मार्टफोन नहीं है?",
    "Call the procurement helpline from any phone to hear your slot and payment status, or ask "
    "the operator at your nearest Common Service Centre to register you.":
        "किसी भी फोन से खरीद हेल्पलाइन पर कॉल करके अपने स्लॉट और भुगतान की स्थिति सुनें, या "
        "अपने निकटतम कॉमन सर्विस सेंटर के ऑपरेटर से पंजीकरण करवाएं।",
    "Staff sign in": "कर्मचारी लॉगिन",

    # login / otp
    "Registered mobile number": "पंजीकृत मोबाइल नंबर",
    "A one-time password will be sent to this number.":
        "इस नंबर पर एक ओटीपी भेजा जाएगा।",
    "Send OTP": "ओटीपी भेजें",
    "Not registered yet?": "अभी तक पंजीकरण नहीं किया?",
    "Create an account": "खाता बनाएं",
    "Verify one-time password": "ओटीपी सत्यापित करें",
    "Enter 6-digit OTP": "6 अंकों का ओटीपी दर्ज करें",
    "Verify and sign in": "सत्यापित करें और लॉगिन करें",
    "Use a different number": "दूसरा नंबर उपयोग करें",

    # registration / profile fields
    "Farmer registration": "किसान पंजीकरण",
    "Your details": "आपकी जानकारी",
    "Full name (as printed on the bank passbook)":
        "पूरा नाम (जैसा बैंक पासबुक में छपा है)",
    "Mobile number": "मोबाइल नंबर",
    "Village / town": "गांव / कस्बा",
    "District": "जिला",
    "-- Select district --": "-- जिला चुनें --",
    "Aadhaar number": "आधार नंबर",
    "Bank account number": "बैंक खाता संख्या",
    "IFSC code": "आईएफएससी कोड",
    "Name printed on the bank account": "बैंक खाते में दर्ज नाम",
    "Land record ID": "भूमि रिकॉर्ड संख्या",
    "My details": "मेरी जानकारी",
    "Edit details": "जानकारी बदलें",
    "Save and re-check": "सहेजें और दोबारा जांचें",
    "Back to dashboard": "डैशबोर्ड पर वापस",
    "Cancel": "रद्द करें",
    "All checks passed": "सभी जांच सफल",

    # dashboard
    "Upcoming slots": "आने वाले स्लॉट",
    "Received": "प्राप्त",
    "Awaiting payment": "भुगतान बाकी",
    "Open detail issues": "जानकारी में समस्याएं",
    "Upcoming bookings": "आने वाली बुकिंग",
    "Book a new slot": "नया स्लॉट बुक करें",
    "Recent history": "पिछला रिकॉर्ड",
    "Latest alerts": "नई सूचनाएं",
    "View all": "सभी देखें",
    "All payments": "सभी भुगतान",
    "You have no upcoming slots.": "आपका कोई आने वाला स्लॉट नहीं है।",
    "Find a procurement centre": "खरीद केंद्र खोजें",
    "No completed procurement yet.": "अभी तक कोई खरीद पूरी नहीं हुई।",
    "No alerts yet.": "अभी कोई सूचना नहीं।",

    # table headings
    "Token": "टोकन",
    "Centre": "केंद्र",
    "Date": "दिनांक",
    "Time": "समय",
    "Crop": "फसल",
    "Est. qty": "अनुमानित मात्रा",
    "Status": "स्थिति",
    "Storage": "भंडारण",
    "Quantity": "मात्रा",
    "Amount": "राशि",
    "Grade": "श्रेणी",
    "Rate": "दर",
    "Payment": "भुगतान",
    "Credited": "जमा",
    "Open": "खोलें",
    "When": "कब",
    "Type": "प्रकार",
    "Channel": "माध्यम",
    "Message": "संदेश",

    # centres / booking
    "Centres in your district are listed first. Choose a centre to see its open slots.":
        "आपके जिले के केंद्र सबसे पहले दिखाए गए हैं। खुले स्लॉट देखने के लिए केंद्र चुनें।",
    "All districts": "सभी जिले",
    "All crops": "सभी फसलें",
    "Filter": "छांटें",
    "Reset": "रीसेट",
    "Crops accepted": "स्वीकार्य फसलें",
    "Daily capacity": "दैनिक क्षमता",
    "Open slots": "खुले स्लॉट",
    "View slots": "स्लॉट देखें",
    "Your district": "आपका जिला",
    "Full": "भरा हुआ",
    "1. Choose a slot": "1. स्लॉट चुनें",
    "2. What are you bringing?": "2. आप क्या ला रहे हैं?",
    "Select": "चुनें",
    "Confirm booking": "बुकिंग पक्की करें",
    "Move to this slot": "इस स्लॉट पर जाएं",
    "Back to centres": "केंद्रों पर वापस",
    "Estimated quantity (quintals)": "अनुमानित मात्रा (क्विंटल)",
    "An estimate is fine. The centre will weigh the actual quantity on arrival.":
        "अनुमान ही काफी है। केंद्र पहुंचने पर असली मात्रा तौली जाएगी।",
    "One slot per farmer per day, and at most three active bookings at a time, so that every "
    "farmer in the district gets a turn.":
        "एक किसान एक दिन में एक ही स्लॉट ले सकता है, और एक समय पर ज्यादा से ज्यादा तीन बुकिंग, "
        "ताकि जिले के हर किसान को मौका मिले।",
    "places free": "जगह खाली",

    # booking detail
    "Slot details": "स्लॉट की जानकारी",
    "Token number": "टोकन नंबर",
    "Procurement centre": "खरीद केंद्र",
    "Reporting time": "पहुंचने का समय",
    "Estimated quantity": "अनुमानित मात्रा",
    "Weighed quantity": "तौली गई मात्रा",
    "Quality grade": "गुणवत्ता श्रेणी",
    "Storage risk": "भंडारण जोखिम",
    "Transaction": "लेनदेन",
    "Rate applied": "लागू दर",
    "Total value": "कुल राशि",
    "Payment status": "भुगतान की स्थिति",
    "Actions": "कार्रवाई",
    "View / print gate pass": "गेट पास देखें / प्रिंट करें",
    "Reschedule this slot": "स्लॉट बदलें",
    "Cancel booking": "बुकिंग रद्द करें",
    "Track payment": "भुगतान देखें",
    "Bring with you": "साथ लाएं",
    "Aadhaar card": "आधार कार्ड",
    "Bank passbook": "बैंक पासबुक",
    "Land record extract": "भूमि रिकॉर्ड की नकल",
    "Storage risk warning": "भंडारण जोखिम चेतावनी",
    "Keep your produce covered": "अपनी उपज को ढककर रखें",
    "Move to an earlier slot if one is free, or store the produce on a raised platform under "
    "a waterproof cover until your slot date.":
        "अगर कोई पहले का स्लॉट खाली है तो उस पर चले जाएं, नहीं तो अपनी उपज को ऊंचे चबूतरे पर "
        "वाटरप्रूफ तिरपाल से ढककर रखें।",

    # gate pass
    "Electronic Gate Pass": "इलेक्ट्रॉनिक गेट पास",
    "GOVERNMENT PROCUREMENT CENTRE": "सरकारी खरीद केंद्र",
    "Farmer": "किसान",
    "Mobile": "मोबाइल",
    "Village / district": "गांव / जिला",
    "Crop declared": "घोषित फसल",
    "Centre address": "केंद्र का पता",
    "Print gate pass": "गेट पास प्रिंट करें",
    "Back to booking": "बुकिंग पर वापस",

    # alerts / payments
    "Alerts and notifications": "सूचनाएं",
    "Payments": "भुगतान",
    "No procurement transactions recorded yet.": "अभी तक कोई खरीद दर्ज नहीं हुई।",

    # flash messages
    "Booking confirmed.": "बुकिंग पक्की हो गई।",
    "Booking cancelled. The slot has been released for other farmers.":
        "बुकिंग रद्द कर दी गई। यह स्लॉट अब दूसरे किसानों के लिए खाली है।",
    "Signed out.": "साइन आउट हो गया।",
    "Please sign in to continue.": "आगे बढ़ने के लिए लॉगिन करें।",
    "Registration complete. Your details passed all verification checks.":
        "पंजीकरण पूरा हुआ। आपकी सारी जानकारी जांच में सही पाई गई।",
    "Saved. All verification checks passed - your payment will not be held up.":
        "सहेज लिया गया। सभी जांच सही हैं, आपका भुगतान नहीं रुकेगा।",
    "Booking confirmed - but a storage risk was detected. See the warning on your booking.":
        "बुकिंग पक्की हो गई, लेकिन भंडारण जोखिम मिला है। अपनी बुकिंग पर चेतावनी देखें।",
    # day names (used by the dayname filter)
    "Today": "आज",
    "Tomorrow": "कल",
    "Monday": "सोमवार", "Tuesday": "मंगलवार", "Wednesday": "बुधवार",
    "Thursday": "गुरुवार", "Friday": "शुक्रवार", "Saturday": "शनिवार", "Sunday": "रविवार",

    # status badges
    "Booked": "बुक", "Arrived": "पहुंच गए", "Completed": "पूरा", "Cancelled": "रद्द",
    "Paid": "भुगतान हुआ", "Processing": "प्रक्रिया में", "Pending": "बाकी", "Failed": "विफल",
    "High risk": "अधिक जोखिम", "Low risk": "कम जोखिम", "None": "कोई नहीं",
    "Grade A": "श्रेणी A", "Grade B": "श्रेणी B", "Rejected": "अस्वीकृत",
    "Centre Staff": "केंद्र कर्मचारी",
    "Voice call": "फोन कॉल", "In app": "ऐप में", "SMS": "एसएमएस",

    # remaining page text
    "One-time registration. You will need your Aadhaar, bank passbook and land record.":
        "एक बार का पंजीकरण। आपको अपना आधार, बैंक पासबुक और भूमि रिकॉर्ड चाहिए होगा।",
    "Why we check your details now": "हम आपकी जानकारी अभी क्यों जांचते हैं",
    "No internet at home?": "घर पर इंटरनेट नहीं है?",
    "Contact your centre to change your registered number.":
        "अपना पंजीकृत नंबर बदलने के लिए अपने केंद्र से संपर्क करें।",
    "For example PUNB0123456.": "जैसे PUNB0123456।",
    "If this differs from the name above, the direct benefit transfer will fail. Leave blank to "
    "copy the name above.":
        "अगर यह ऊपर दिए नाम से अलग है तो भुगतान सीधे खाते में नहीं जा पाएगा। खाली छोड़ने पर "
        "ऊपर वाला नाम ले लिया जाएगा।",
    "Format DDD-NNNNNN-NN, for example KAR-104238-12. Printed on your khasra/khatauni extract.":
        "प्रारूप DDD-NNNNNN-NN, जैसे KAR-104238-12। यह आपकी खसरा/खतौनी की नकल पर लिखा होता है।",
    "These are the details used to verify your identity and credit your payment. Correcting a "
    "flagged field here re-runs the verification checks immediately.":
        "इन्हीं जानकारियों से आपकी पहचान जांची जाती है और भुगतान भेजा जाता है। यहां कोई गलती "
        "सुधारते ही जांच दोबारा चल जाती है।",
    "Your Aadhaar, bank and land-record details are correctly formatted and consistent. Nothing "
    "should hold up your payment.":
        "आपका आधार, बैंक और भूमि रिकॉर्ड सही प्रारूप में हैं और आपस में मेल खाते हैं। आपके "
        "भुगतान में कोई रुकावट नहीं आनी चाहिए।",
    "Every completed procurement and the current state of its payment.":
        "हर पूरी हुई खरीद और उसके भुगतान की मौजूदा स्थिति।",
    "The produce has been weighed at the centre.": "उपज केंद्र पर तौली जा चुकी है।",
}


def get_lang():
    return session.get("lang", "en")


def t(text):
    """Translate one string. Falls back to the english if we have no hindi."""
    if get_lang() == "hi":
        return HINDI.get(text, text)
    return text
