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


@frappe.whitelist()
def get_bom_tree(bom_name):
    """
    Get full BOM tree with all sub-assemblies recursively.
    Returns nested structure with items, quantities, and operations.
    """
    if not bom_name:
        frappe.throw("BOM name is required")

    # Handle if user passes item code instead of BOM name
    if not bom_name.startswith("BOM-"):
        bom_name = frappe.db.get_value("BOM", {"item": bom_name, "is_active": 1, "is_default": 1}, "name")
        if not bom_name:
            bom_name = frappe.db.get_value("BOM", {"item": bom_name, "is_active": 1}, "name")
        if not bom_name:
            return {"error": f"No active BOM found for this item"}

    return _get_bom_tree_recursive(bom_name, level=0)


def _get_bom_tree_recursive(bom_name, level=0, max_level=10):
    """Recursive helper to build BOM tree"""
    if level > max_level:
        return {"error": "Max BOM depth exceeded", "bom": bom_name}

    try:
        bom = frappe.get_doc("BOM", bom_name)
    except frappe.DoesNotExistError:
        return {"error": f"BOM {bom_name} not found"}

    items = []
    for item in bom.items:
        item_data = {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": item.qty,
            "uom": item.uom,
            "rate": item.rate,
            "amount": item.amount,
            "is_sub_assembly": bool(item.bom_no)
        }

        # If this item has its own BOM, get it recursively
        if item.bom_no:
            item_data["bom"] = _get_bom_tree_recursive(item.bom_no, level + 1, max_level)

        items.append(item_data)

    # Get operations if any
    operations = []
    for op in bom.operations:
        operations.append({
            "operation": op.operation,
            "workstation": op.workstation,
            "time_in_mins": op.time_in_mins,
            "operating_cost": op.operating_cost
        })

    return {
        "bom": bom_name,
        "item": bom.item,
        "item_name": bom.item_name,
        "quantity": bom.quantity,
        "uom": bom.uom,
        "docstatus": bom.docstatus,
        "status": "Draft" if bom.docstatus == 0 else ("Submitted" if bom.docstatus == 1 else "Cancelled"),
        "is_active": bom.is_active,
        "is_default": bom.is_default,
        "total_cost": bom.total_cost,
        "items": items,
        "operations": operations,
        "level": level
    }


@frappe.whitelist()
def get_bom_status(bom_name):
    """
    Get BOM status and what actions user can perform.
    """
    if not bom_name:
        frappe.throw("BOM name is required")

    try:
        bom = frappe.get_doc("BOM", bom_name)
    except frappe.DoesNotExistError:
        return {"error": f"BOM {bom_name} not found"}

    user = frappe.session.user
    can_cancel = frappe.has_permission("BOM", "cancel", user=user)
    can_write = frappe.has_permission("BOM", "write", user=user)

    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}

    return {
        "bom": bom_name,
        "item": bom.item,
        "docstatus": bom.docstatus,
        "status": status_map.get(bom.docstatus, "Unknown"),
        "can_edit": bom.docstatus == 0 and can_write,
        "can_cancel": bom.docstatus == 1 and can_cancel,
        "can_submit": bom.docstatus == 0 and can_write,
        "message": _get_status_message(bom.docstatus, can_cancel, can_write)
    }


def _get_status_message(docstatus, can_cancel, can_write):
    """Get helpful message based on status and permissions"""
    if docstatus == 0:
        return "BOM is draft. Can be edited and submitted."
    elif docstatus == 1:
        if can_cancel:
            return "BOM is submitted. Cancel it to make changes."
        else:
            return "BOM is submitted. Ask admin to cancel it for modifications."
    else:
        return "BOM is cancelled. Create a new BOM if needed."


@frappe.whitelist()
def create_bom_tree(tree_data):
    """
    Create entire BOM tree from nested structure.
    Creates BOMs bottom-up (leaf nodes first, then parents).

    Input format:
    {
        "item": "DINING-TABLE",
        "quantity": 1,
        "items": [
            {
                "item_code": "TOP-ASSY",
                "qty": 1,
                "is_sub_assembly": true,
                "bom": {
                    "item": "TOP-ASSY",
                    "items": [
                        {"item_code": "PLYWOOD", "qty": 2, "uom": "Sqm"},
                        {"item_code": "LAMINATE", "qty": 2, "uom": "Sqm"}
                    ]
                }
            },
            {"item_code": "SCREW-M6", "qty": 16, "uom": "Nos"}
        ]
    }
    """
    import json
    if isinstance(tree_data, str):
        tree_data = json.loads(tree_data)

    created_boms = []
    errors = []

    try:
        _create_bom_recursive(tree_data, created_boms, errors)
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "created_boms": created_boms,
            "errors": errors
        }

    if errors:
        return {
            "success": False,
            "errors": errors,
            "created_boms": created_boms
        }

    return {
        "success": True,
        "created_boms": created_boms,
        "message": f"Created {len(created_boms)} BOM(s) as draft"
    }


def _create_bom_recursive(tree_data, created_boms, errors):
    """Recursive helper to create BOMs bottom-up"""
    items_for_bom = []

    for item in tree_data.get("items", []):
        item_code = item.get("item_code")
        qty = item.get("qty", 1)
        uom = item.get("uom")

        # If no UOM provided, get default from Item master
        if not uom:
            uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"

        # If this is a sub-assembly, create its BOM first
        if item.get("is_sub_assembly") and item.get("bom"):
            child_bom_name = _create_bom_recursive(item["bom"], created_boms, errors)
            if child_bom_name:
                items_for_bom.append({
                    "item_code": item_code,
                    "qty": qty,
                    "uom": uom,
                    "bom_no": child_bom_name
                })
        else:
            items_for_bom.append({
                "item_code": item_code,
                "qty": qty,
                "uom": uom
            })

    # Now create this BOM
    main_item = tree_data.get("item")
    if not main_item:
        errors.append("Missing 'item' in tree data")
        return None

    try:
        bom = frappe.new_doc("BOM")
        bom.item = main_item
        bom.quantity = tree_data.get("quantity", 1)
        bom.is_active = 1
        bom.is_default = tree_data.get("is_default", 1)

        for item_data in items_for_bom:
            bom.append("items", item_data)

        # Add operations if provided
        for op in tree_data.get("operations", []):
            bom.append("operations", {
                "operation": op.get("operation"),
                "workstation": op.get("workstation"),
                "time_in_mins": op.get("time_in_mins", 0)
            })

        bom.insert()
        created_boms.append({
            "bom": bom.name,
            "item": main_item,
            "status": "Draft"
        })
        return bom.name

    except Exception as e:
        errors.append(f"Error creating BOM for {main_item}: {str(e)}")
        return None


@frappe.whitelist()
def cancel_and_amend_bom(bom_name, changes=None):
    """
    Cancel a submitted BOM and create an amended version with changes.

    changes format:
    {
        "items": [
            {"item_code": "PLYWOOD", "qty": 2.5}  # update qty
        ],
        "add_items": [
            {"item_code": "NEW-ITEM", "qty": 1, "uom": "Nos"}
        ],
        "remove_items": ["OLD-ITEM"]
    }
    """
    import json
    if isinstance(changes, str):
        changes = json.loads(changes) if changes else {}

    if not bom_name:
        frappe.throw("BOM name is required")

    try:
        bom = frappe.get_doc("BOM", bom_name)
    except frappe.DoesNotExistError:
        return {"success": False, "error": f"BOM {bom_name} not found"}

    # Check if submitted
    if bom.docstatus != 1:
        return {"success": False, "error": "BOM is not submitted. Edit it directly."}

    # Check cancel permission
    if not frappe.has_permission("BOM", "cancel"):
        return {"success": False, "error": "You don't have permission to cancel BOM. Ask your administrator."}

    try:
        # Cancel the old BOM
        bom.cancel()

        # Create amended version
        new_bom = frappe.copy_doc(bom)
        new_bom.docstatus = 0
        new_bom.amended_from = bom.name

        # Apply changes
        if changes:
            # Update item quantities
            for change in changes.get("items", []):
                for item in new_bom.items:
                    if item.item_code == change.get("item_code"):
                        if "qty" in change:
                            item.qty = change["qty"]
                        if "uom" in change:
                            item.uom = change["uom"]

            # Remove items
            for item_code in changes.get("remove_items", []):
                new_bom.items = [i for i in new_bom.items if i.item_code != item_code]

            # Add new items
            for new_item in changes.get("add_items", []):
                new_bom.append("items", new_item)

        new_bom.insert()

        return {
            "success": True,
            "cancelled_bom": bom_name,
            "new_bom": new_bom.name,
            "status": "Draft",
            "message": f"Cancelled {bom_name}, created {new_bom.name} as draft"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
