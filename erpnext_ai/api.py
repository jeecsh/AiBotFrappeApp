import frappe
from frappe.utils.password import get_decrypted_password


@frappe.whitelist()
def get_credentials():
    """
    Get or generate API credentials for the current user.
    Returns api_key and api_secret that the AI backend can use.
    """
    user = frappe.session.user

    if user == "Guest":
        frappe.throw("Please login first")

    # Get existing API key
    api_key = frappe.db.get_value("User", user, "api_key")

    if not api_key:
        # Auto-generate API key and secret
        api_key = frappe.generate_hash(length=15)
        api_secret = frappe.generate_hash(length=15)

        user_doc = frappe.get_doc("User", user)
        user_doc.api_key = api_key
        user_doc.api_secret = api_secret
        user_doc.save(ignore_permissions=True)
        frappe.db.commit()
    else:
        # Decrypt existing secret
        api_secret = get_decrypted_password("User", user, "api_secret")

        if not api_secret:
            # Secret missing, regenerate it
            api_secret = frappe.generate_hash(length=15)
            user_doc = frappe.get_doc("User", user)
            user_doc.api_secret = api_secret
            user_doc.save(ignore_permissions=True)
            frappe.db.commit()

    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "user": user
    }
