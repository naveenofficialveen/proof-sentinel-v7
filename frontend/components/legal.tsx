export type LegalDoc = "terms" | "privacy";

export const LEGAL: Record<LegalDoc, { title: string; sections: [string, string][] }> = {
  terms: {
    title: "Terms & Conditions",
    sections: [
      ["1. About this service", "The Digital Proof Verification and Evidence Analysis System lets you upload files, read their technical metadata, calculate SHA-256 hashes, extract text with OCR, and download technical reports. It is an academic project. Its output is technical information only. It is not legal advice and it is not a certified forensic opinion."],
      ["2. Your account", "You are responsible for keeping your password private and for everything done through your account. Administrators can lock an account. A locked account cannot use protected features until it is unlocked."],
      ["3. What you may upload", "Upload only files you own or are allowed to handle. Do not upload unlawful content. Do not try to break, overload or bypass the security of the service, and do not try to reach another user's data."],
      ["4. Metadata Editor and Metadata Remover", "These tools never change your original upload. They create a new copy. Copies made by the Editor are labelled as edited, the change is recorded in your report and in the security log, and the original keeps its own SHA-256 hash. You must not present an edited copy as the original or use it to mislead any court, employer, authority or other person."],
      ["5. Accuracy of results", "Metadata can be missing, wrong or edited by anyone, so it does not prove who created a file, which device captured it, or when. OCR can make mistakes. Signature checks are limited: if a signature could not be verified, the report says so."],
      ["6. No warranty", "The service is provided as is, without any promise that it is error free or always available. Keep your own copy of important files."],
      ["7. Ending access", "Administrators may lock or remove accounts that break these terms."],
      ["8. Changes", "These terms may be updated. Using the service after an update means you accept the new terms."],
    ],
  },
  privacy: {
    title: "Privacy Policy",
    sections: [
      ["1. What we collect", "Your name and email address, your password (stored only as a salted hash, never as text), the files you upload, the results of analysing them (metadata, OCR text, hashes, file structure, signature status), the reports generated for you, and security log entries such as sign-in, upload, analysis, report, download and metadata-tool events with the time and your IP address."],
      ["2. Why we collect it", "To run your account, analyse your files, create your reports, and keep an audit trail that protects the service and its users."],
      ["3. Who can see it", "Only you can open your files, results and reports. Administrators manage the service and can see account details, file names, types, sizes, hashes, processing status, report records and the security log. The person who runs the server also has technical access to stored data."],
      ["4. Cookies", "We use one essential session cookie to keep you signed in. It cannot be read by page scripts. We do not use advertising or tracking cookies."],
      ["5. Email", "Your email address is used to identify your account and to send one-time codes when you reset your password."],
      ["6. Other services", "Page fonts are loaded from Google Fonts, so your browser contacts Google when the page opens. If email delivery is switched on, the email provider handles the code messages."],
      ["7. How long we keep data", "Files, results and reports are kept on the server until the person who runs the service removes them. Ask the administrator if you want your data deleted."],
      ["8. Security", "Passwords are hashed, access is limited to your own account, password codes expire and can only be tried a few times, and uploaded files are stored under random names. No system is completely secure."],
      ["9. Contact", "For questions or deletion requests, contact the administrator of this service."],
    ],
  },
};
