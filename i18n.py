"""Hindi translations.

Keyed on the english string so templates stay readable - {{ t("Book a Slot") }}.
If a string is missing from the dict it just falls back to english, so a half
finished translation doesn't break the page.

Only the farmer side is translated. Centre staff use the english admin screens.
TODO: move this to flask-babel if we ever add a third language
"""

from flask import session

HINDI = {
    'Indicative rates per quintal, and the rise over the previous season': 'प्रति क्विंटल सांकेतिक दरें, और पिछले सत्र से बढ़ोतरी',
    "Nothing yet": "अभी कुछ नहीं",
    # home weather overview
    'Next three days, every procurement district': 'अगले तीन दिन, सभी खरीद जिले',
    'Reading at': 'रीडिंग का स्थान',
    'Rain today': 'आज बारिश',
    'Rain, 3 days': 'बारिश, 3 दिन',
    'Humidity': 'नमी',
    'Keep grain covered': 'अनाज ढककर रखें',
    'Pick a district for its five-day forecast.': 'पांच दिन का पूर्वानुमान देखने के लिए जिला चुनें।',
    'No forecast available right now.': 'अभी पूर्वानुमान उपलब्ध नहीं है।',
    # gate pass form
    'Government procurement centre': 'सरकारी खरीद केंद्र',
    'Form': 'प्रपत्र',
    'Serial no.': 'क्रम संख्या',
    'Farmer copy': 'किसान प्रति',
    'Office copy': 'कार्यालय प्रति',
    'Particulars': 'विवरण',
    'To be filled at the weighbridge': 'तौल कांटे पर भरा जाएगा',
    'Weighed quantity (quintals)': 'तौली गई मात्रा (क्विंटल)',
    'Weighbridge clerk': 'तौल लिपिक',
    'Centre stamp': 'केंद्र की मुहर',
    'Farmer signature or thumb impression': 'किसान के हस्ताक्षर या अंगूठा निशान',
    'Cut along this line. The office copy stays at the centre.': 'इस रेखा पर काटें। कार्यालय प्रति केंद्र पर रहेगी।',
    'Slot': 'स्लॉट',
    "Registration no.": "पंजीकरण संख्या",
    # home page notice board
    'Book a weighing slot at your procurement centre': 'अपने खरीद केंद्र पर तौल का स्लॉट बुक करें',
    'Choose a day and time, get a token, and bring your crop when it is your turn. Your Aadhaar and bank details are checked when you register, so your payment is not held up later.': 'दिन और समय चुनें, टोकन पाएं, और अपनी बारी पर उपज लेकर आएं। पंजीकरण के समय ही आपके आधार और बैंक विवरण की जांच हो जाती है, ताकि बाद में भुगतान न रुके।',
    'Minimum Support Price': 'न्यूनतम समर्थन मूल्य',
    'RMS 2025-26, indicative rates per quintal': 'रबी विपणन सत्र 2025-26, प्रति क्विंटल सांकेतिक दरें',
    'Before you come': 'आने से पहले',
    'Gate pass or token number': 'गेट पास या टोकन नंबर',
    'Kisan Call Centre': 'किसान कॉल सेंटर',
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
    "Next free slot": "अगला खाली स्लॉट",
    "No centres match that filter.": "इस फ़िल्टर से कोई केंद्र नहीं मिला।",
    "Fully booked": "पूरा भरा है",
    "Only": "केवल",
    "left": "बचे हैं",
    "Your own district is listed first, but you can book at any centre that procures your crop. "
    "Bring your Aadhaar card and bank passbook on the day.":
        "आपका अपना जिला पहले दिखाया गया है, लेकिन आप किसी भी ऐसे केंद्र पर बुक कर सकते हैं जो "
        "आपकी फसल खरीदता हो। स्लॉट वाले दिन आधार कार्ड और बैंक पासबुक साथ लाएं।",

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

    # redesign: home sections, sign-in, booking progress, dashboards
    "12 digits, no spaces. Checked against the standard Aadhaar checksum.": "12 अंक, बिना खाली जगह के। आधार के मानक चेकसम से जांचा जाता है।",
    "A slot was confirmed or moved.": "स्लॉट पक्का हुआ या बदला गया।",
    "Aadhaar and bank": "आधार और बैंक",
    "Aadhaar checksum, IFSC format and the name on your bank account, before a payment can bounce.": "भुगतान अटकने से पहले ही आधार चेकसम, IFSC का प्रारूप और बैंक खाते पर लिखा नाम जांच लिया जाता है।",
    "Action needed": "ध्यान दें",
    "An OTP has been sent to": "OTP भेजा गया है",
    "Any Common Service Centre operator or procurement centre clerk can complete this registration on your behalf.": "कोई भी जन सेवा केंद्र (CSC) संचालक या खरीद केंद्र का कर्मचारी आपकी ओर से यह पंजीकरण कर सकता है।",
    "At the centre": "केंद्र पर",
    "Available": "उपलब्ध",
    "Bank account and IFSC": "बैंक खाता और IFSC",
    "Book a slot": "स्लॉट बुक करें",
    "Book a weighing slot, get your details checked before they can hold up a payment, and follow your money to your account.": "तौल का स्लॉट बुक करें, भुगतान अटकने से पहले अपनी जानकारी जंचवाएं, और अपने पैसे को खाते तक आते देखें।",
    "Book your slot.": "स्लॉट बुक करें।",
    "Book, move or cancel a slot": "स्लॉट बुक करें, बदलें या रद्द करें",
    "Booking": "बुकिंग",
    "Built around what actually goes wrong at the mandi": "मंडी में असल में जो गड़बड़ होती है, उसी को ध्यान में रखकर बनाया गया",
    "Calls in Hindi": "हिंदी में कॉल",
    "Calls in Hindi, no smartphone needed": "हिंदी में कॉल, स्मार्टफोन की ज़रूरत नहीं",
    "Checked at registration": "पंजीकरण के समय ही जांच",
    "Checked the moment you save. Getting these right is what stops your payment being held.": "सहेजते ही जांच होती है। इन्हें सही रखने से आपका भुगतान नहीं रुकता।",
    "Choose a slot": "स्लॉट चुनें",
    "Choose your district": "अपना जिला चुनें",
    "Clear flagged records before they hold up a payment": "भुगतान रुकने से पहले गलत रिकॉर्ड ठीक करें",
    "Correct my details": "मेरी जानकारी सुधारें",
    "Credited on": "जमा होने की तारीख",
    "Demonstration document, not a government-issued instrument.": "यह प्रदर्शन के लिए बना दस्तावेज़ है, सरकारी दस्तावेज़ नहीं।",
    "Demonstration prototype": "प्रदर्शन प्रोटोटाइप",
    "Details checked at sign-up": "पंजीकरण पर ही जानकारी की जांच",
    "Details to fix": "सुधारने योग्य जानकारी",
    "Details verified, payment will not be held": "जानकारी सही है, भुगतान नहीं रुकेगा",
    "Everything about your slots and payments, in one place.": "आपके स्लॉट और भुगतान की पूरी जानकारी, एक ही जगह।",
    "Everything the portal has sent you. Entries marked voice call are the messages the telephone helpline reads out to farmers without a smartphone.": "पोर्टल ने आपको जो कुछ भेजा है, सब यहां है। वॉइस कॉल वाले संदेश वे हैं जो बिना स्मार्टफोन वाले किसानों को फोन पर सुनाए जाते हैं।",
    "FAQ": "FAQ",
    "Farmers sign in with the mobile number they registered, and any OTP works - try": "किसान अपने पंजीकृत मोबाइल नंबर से लॉगिन करें, कोई भी OTP चलेगा - जैसे",
    "Fix problems early": "गड़बड़ी पहले ही ठीक करें",
    "Follow your payment to the bank": "भुगतान को बैंक तक पहुंचते देखें",
    "From harvest to bank account in four steps": "फसल से बैंक खाते तक, चार कदमों में",
    "Gate pass": "गेट पास",
    "Gate pass with QR code": "QR कोड वाला गेट पास",
    "Get paid": "भुगतान पाएं",
    "Get paid on time.": "समय पर भुगतान पाएं।",
    "Get rain and payment alerts": "बारिश और भुगतान की सूचना पाएं",
    "Government procurement at MSP": "MSP पर सरकारी खरीद",
    "Hindi and English": "हिंदी और अंग्रेज़ी",
    "How it works": "यह कैसे काम करता है",
    "If a detail would stop your payment, you find out now, not weeks after you sell.": "अगर कोई जानकारी भुगतान रोक सकती है, तो आपको अभी पता चलेगा, बेचने के हफ्तों बाद नहीं।",
    "If rain is due while your harvest waits at home, we tell you, and which town the reading came from.": "अगर घर पर रखी उपज के दौरान बारिश आने वाली है, तो हम बताते हैं, और यह भी कि मौसम की जानकारी किस शहर से ली गई।",
    "Issued": "जारी",
    "Keep these in front of you": "ये साथ रखें",
    "Land": "भूमि",
    "Main menu": "मुख्य मेनू",
    "Money credited": "पैसा जमा",
    "Most delayed procurement payments are not caused by the procurement itself. They are caused by an Aadhaar digit typed wrong, an IFSC that does not exist, or a bank account in a relative's name.": "ज़्यादातर खरीद भुगतान खरीद की वजह से नहीं रुकते। वे रुकते हैं आधार का एक अंक गलत लिखने से, ऐसे IFSC से जो मौजूद ही नहीं, या किसी रिश्तेदार के नाम वाले बैंक खाते से।",
    "Namaste": "नमस्ते",
    "Name matches the bank": "नाम बैंक से मेल खाता है",
    "Needs fixing": "सुधार ज़रूरी",
    "Next five days": "अगले पांच दिन",
    "No SMS is actually sent in this prototype - use": "इस प्रोटोटाइप में असल में SMS नहीं भेजा जाता - इस्तेमाल करें",
    "No further action is possible on this booking.": "इस बुकिंग पर अब कोई कार्रवाई नहीं हो सकती।",
    "No slots have been published for this centre yet.": "इस केंद्र के लिए अभी कोई स्लॉट जारी नहीं हुआ है।",
    "No smartphone needed. Centre staff can ring you and read out your slot and token number.": "स्मार्टफोन की ज़रूरत नहीं। केंद्र कर्मचारी आपको फोन करके स्लॉट और टोकन नंबर बता सकते हैं।",
    "One more step": "बस एक कदम और",
    "One slot per day, up to three active bookings.": "एक दिन में एक स्लॉट, एक साथ अधिकतम तीन बुकिंग।",
    "Page not found": "पेज नहीं मिला",
    "Passed checks": "जांच में सही",
    "Payment held": "भुगतान रुका",
    "Payment history": "भुगतान का इतिहास",
    "Payments are credited by direct benefit transfer to the bank account registered against your Aadhaar. If a payment shows as failed, the cause is almost always a detail mismatch - check": "भुगतान सीधे आपके आधार से जुड़े बैंक खाते में (DBT) भेजा जाता है। अगर भुगतान विफल दिखे, तो वजह लगभग हमेशा जानकारी का मेल न खाना होता है - जांचें",
    "Payments held": "रुके हुए भुगतान",
    "Pick a centre and a time that suits you.": "अपनी सुविधा का केंद्र और समय चुनें।",
    "Pick a centre, a day and a two-hour window. You get a token and a gate pass to print.": "केंद्र, दिन और दो घंटे का समय चुनें। आपको टोकन और छापने के लिए गेट पास मिलेगा।",
    "Pick a new slot below. Your token number will be reissued.": "नीचे नया स्लॉट चुनें। आपका टोकन नंबर दोबारा जारी होगा।",
    "Please check": "कृपया जांचें",
    "Present this pass with your Aadhaar card and bank passbook at the centre gate. Valid only for the date and time window shown above.": "केंद्र के गेट पर यह पास आधार कार्ड और बैंक पासबुक के साथ दिखाएं। यह केवल ऊपर लिखी तारीख और समय के लिए मान्य है।",
    "Progress": "प्रगति",
    "Queue": "कतार",
    "Rain is due while your harvest waits.": "उपज रखे रहने के दौरान बारिश आने वाली है।",
    "Rain warnings": "बारिश की चेतावनी",
    "Rain warnings before your slot": "स्लॉट से पहले बारिश की चेतावनी",
    "Record weight and grade, then close the transaction": "वज़न और ग्रेड दर्ज करें, फिर लेनदेन पूरा करें",
    "Register as a farmer": "किसान के रूप में पंजीकरण करें",
    "Register once": "एक बार पंजीकरण",
    "Rescheduling booking": "बुकिंग का समय बदल रहे हैं",
    "Return to home": "होम पर लौटें",
    "Ring a farmer in Hindi from any booking": "किसी भी बुकिंग से किसान को हिंदी में फोन करें",
    "Secure sign in": "सुरक्षित लॉगिन",
    "See how many farmers are ahead of you in your window, and whether the centre is running late.": "देखें कि आपके समय में आपसे आगे कितने किसान हैं, और केंद्र देरी से तो नहीं चल रहा।",
    "See your place in the queue": "कतार में अपनी जगह देखें",
    "See your upcoming slots": "अपने आने वाले स्लॉट देखें",
    "Simulated OTP.": "नकली OTP।",
    "Skip the queue.": "कतार से बचें।",
    "Slot booked": "स्लॉट बुक",
    "Slot change": "स्लॉट में बदलाव",
    "Something in your details could hold up a payment.": "आपकी जानकारी में कुछ ऐसा है जो भुगतान रोक सकता है।",
    "Something went wrong": "कुछ गड़बड़ हो गई",
    "Staff sign-in:": "कर्मचारी लॉगिन:",
    "Step 1 of 2": "चरण 1 / 2",
    "Step 2 of 2": "चरण 2 / 2",
    "Switch language at the top of any page, and make the text bigger if you need to.": "किसी भी पेज के ऊपर भाषा बदलें, और ज़रूरत हो तो अक्षर बड़े करें।",
    "Takes about five minutes": "लगभग पांच मिनट लगते हैं",
    "This booking was cancelled and its place given back.": "यह बुकिंग रद्द हो गई है और इसकी जगह दूसरों के लिए खोल दी गई है।",
    "This payment could not be credited. Check": "यह भुगतान खाते में नहीं जा सका। जांचें",
    "Those mismatches are normally discovered weeks after the produce is sold. This portal checks them the moment you register, so there is time to fix them before your slot.": "ऐसी गड़बड़ियां आम तौर पर उपज बिकने के हफ्तों बाद पकड़ में आती हैं। यह पोर्टल पंजीकरण करते ही इन्हें जांच लेता है, ताकि स्लॉट से पहले इन्हें ठीक करने का समय मिल जाए।",
    "Track every payment": "हर भुगतान पर नज़र रखें",
    "Transaction closed": "लेनदेन पूरा",
    "Transactions": "लेनदेन",
    "Two-hour windows, two weeks ahead": "दो घंटे के स्लॉट, दो हफ्ते आगे तक",
    "Use the mobile number you registered with. The OTP is not really sent anywhere yet, so any six digits get you in.": "वही मोबाइल नंबर डालें जिससे पंजीकरण किया था। अभी OTP असल में कहीं नहीं भेजा जाता, इसलिए कोई भी छह अंक चलेंगे।",
    "Used to check the quantity you bring is reasonable.": "इससे जांचा जाता है कि लाई गई मात्रा उचित है।",
    "We check it is really you before showing your bank and payment details.": "बैंक और भुगतान की जानकारी दिखाने से पहले हम जांचते हैं कि यह सच में आप ही हैं।",
    "Weather": "मौसम",
    "Weather before your slot": "स्लॉट से पहले का मौसम",
    "Weighed at centre": "केंद्र पर तौल",
    "Welcome back": "फिर से स्वागत है",
    "What are you bringing?": "आप क्या ला रहे हैं?",
    "What makes it different": "यह अलग क्यों है",
    "What these mean": "इनका मतलब",
    "Who you are": "आपकी पहचान",
    "You will see rain and humidity for the next five days.": "आपको अगले पांच दिन की बारिश और नमी दिखेगी।",
    "Your crop is weighed and graded at the gate, and you can follow the payment to your account.": "गेट पर आपकी फसल तौली और ग्रेड की जाती है, और आप भुगतान को अपने खाते तक पहुंचते देख सकते हैं।",
    "Your crop was weighed, or money moved.": "आपकी फसल तौली गई, या पैसा आगे बढ़ा।",
    "Your mobile number, Aadhaar, bank account and land record. Checked the moment you submit.": "आपका मोबाइल नंबर, आधार, बैंक खाता और भूमि रिकॉर्ड। जमा करते ही जांच।",
    "Your name exactly as the bank has it.": "आपका नाम ठीक वैसा ही जैसा बैंक में दर्ज है।",
    "Your produce can still be procured, but your payment will be held until these are corrected.": "आपकी उपज फिर भी खरीदी जा सकती है, लेकिन इन्हें ठीक होने तक भुगतान रुका रहेगा।",
    "Your produce has been weighed at the centre. The transaction will be closed shortly.": "आपकी उपज केंद्र पर तौली जा चुकी है। लेनदेन जल्द पूरा होगा।",
    "for unresolved issues, or visit your procurement centre.": "में बची हुई गड़बड़ियां देखें, या अपने खरीद केंद्र जाएं।",
    "issue(s) found": "गड़बड़ी मिली",
    "per quintal": "प्रति क्विंटल",
    "problem(s) with your registered details": "आपकी पंजीकृत जानकारी में गड़बड़ी",
    "qtl": "क्विं.",
    "quintals": "क्विंटल",
    "quintals a day": "क्विंटल प्रतिदिन",
    "rain": "बारिश",
    "Wheat": "गेहूं",
    "Paddy": "धान",
    "Mustard": "सरसों",
    "Gram": "चना",
    "Maize": "मक्का",
    "Bajra": "बाजरा",
    "Jan": "जन",
    "Feb": "फर",
    "Mar": "मार्च",
    "Apr": "अप्रै",
    "May": "मई",
    "Jun": "जून",
    "Jul": "जुला",
    "Aug": "अग",
    "Sep": "सित",
    "Oct": "अक्टू",
    "Nov": "नव",
    "Dec": "दिस",
    "Blocking": "भुगतान रोकने वाली",
    "Warning": "चेतावनी",
    "Aadhaar": "आधार",
    "Bank": "बैंक",
    "Name Match": "नाम का मेल",
    "Terms of use": "उपयोग की शर्तें",
    "Privacy policy": "गोपनीयता नीति",
    "Copyright policy": "कॉपीराइट नीति",
    "Hyperlinking policy": "हाइपरलिंक नीति",
    "Accessibility statement": "सुलभता विवरण",

    # place names, weather words, farmer flashes, trimmed labels
    "Rudrapur Mandi Samiti": "रुद्रपुर मंडी समिति",
    "Kichha Kharid Kendra": "किच्छा खरीद केंद्र",
    "Haridwar Kharid Kendra": "हरिद्वार खरीद केंद्र",
    "Vikasnagar Grain Market": "विकासनगर अनाज मंडी",
    "Haldwani Mandi Centre": "हल्द्वानी मंडी केंद्र",
    "Rudrapur": "रुद्रपुर",
    "Kichha Block": "किच्छा ब्लॉक",
    "Kichha": "किच्छा",
    "Jwalapur": "ज्वालापुर",
    "Vikasnagar": "विकासनगर",
    "Mandi Road, Haldwani": "मंडी रोड, हल्द्वानी",
    "Haldwani": "हल्द्वानी",
    "Dineshpur": "दिनेशपुर",
    "Manglaur": "मंगलौर",
    "Gadarpur": "गदरपुर",
    "Udham Singh Nagar": "उधम सिंह नगर",
    "Haridwar": "हरिद्वार",
    "Dehradun": "देहरादून",
    "Nainital": "नैनीताल",
    "clear sky": "साफ आसमान",
    "few clouds": "हल्के बादल",
    "scattered clouds": "छिटपुट बादल",
    "broken clouds": "बादल छाए",
    "overcast clouds": "घने बादल",
    "light rain": "हल्की बारिश",
    "moderate rain": "मध्यम बारिश",
    "heavy intensity rain": "तेज़ बारिश",
    "very heavy rain": "बहुत तेज़ बारिश",
    "shower rain": "बौछारें",
    "light intensity shower rain": "हल्की बौछारें",
    "thunderstorm": "आंधी-तूफान",
    "thunderstorm with light rain": "गरज के साथ हल्की बारिश",
    "drizzle": "बूंदाबांदी",
    "light intensity drizzle": "हल्की बूंदाबांदी",
    "mist": "धुंध",
    "haze": "धुंध",
    "fog": "कोहरा",
    "Booking confirmed. Your token is %s.": "बुकिंग पक्की। आपका टोकन %s है।",
    "No farmer is registered with %s. Please register first.": "%s से कोई किसान पंजीकृत नहीं है। पहले पंजीकरण करें।",
    "Signed in as %s.": "%s के रूप में लॉगिन हुआ।",
    "Incorrect OTP. For this demo the OTP is always %s.": "गलत OTP। इस डेमो में OTP हमेशा %s है।",
    "Registered, but we found %d issue(s) in your details. See the notice on your dashboard.": "पंजीकरण हो गया, पर आपकी जानकारी में %d गड़बड़ी मिली। डैशबोर्ड देखें।",
    "Slot rescheduled to %s, %s.": "स्लॉट बदलकर %s, %s कर दिया गया।",
    "Saved. %d issue(s) still need attention.": "सहेजा गया। %d गड़बड़ी अभी बाकी है।",
    "Invalid booking request.": "बुकिंग का अनुरोध सही नहीं है।",
    "Invalid slot.": "स्लॉट सही नहीं है।",
    "Sample": "नमूना",
    "No smartphone? Any CSC centre can register you.": "स्मार्टफोन नहीं है? किसी भी CSC केंद्र पर पंजीकरण कराएं।",
    "Keep these ready": "ये तैयार रखें",
    "12 digits": "12 अंक",
    "As printed in the passbook": "पासबुक में जैसा लिखा है",
    "For example USN-104238-12": "जैसे USN-104238-12",
    "Demo OTP:": "डेमो OTP:",
    "Prototype. All data shown is sample data.": "प्रोटोटाइप। दिखाई गई सारी जानकारी नमूना है।",
    "Show this pass with your Aadhaar card and bank passbook.": "यह पास आधार कार्ड और बैंक पासबुक के साथ दिखाएं।",
    "Not allowed": "अनुमति नहीं",
}


def get_lang():
    return session.get("lang", "en")


def t(text):
    """Translate one string. Falls back to the english if we have no hindi."""
    if get_lang() == "hi":
        return HINDI.get(text, text)
    return text
