from tracker import Tracker, site_name
import config
import email_setup

tracker = Tracker()


def show_menu():
    print("\n===== DropScout: Track. Drop. Save =====")
    print("1. Add a product")
    print("2. Remove a product")
    print("3. Show tracked products")
    print("4. Show price history of a product")
    print("5. Check prices now")
    print("6. Start automatic checking (scheduler)")
    print("7. Show alert log")
    print("8. Email settings")
    print("9. Compare prices across sites")
    print("10. Exit")


def show_products():
    products = tracker.db.get_all_products()
    if len(products) == 0:
        print("No products tracked yet.")
    else:
        for product in products:
            last_price = tracker.db.get_last_price(product["id"])
            group_text = ""
            if product["group_name"] is not None:
                group_text = "  [group: " + product["group_name"] + "]"
            print(str(product["id"]) + ". " + product["name"][:60] + group_text)
            print("   Current: " + str(last_price) + " | Target: " + str(product["target_price"])
                  + " | " + str(product["availability"]))


def add_product():
    url = input("Product URL: ")
    target_text = input("Target price: ")
    errors = []
    target_price = 0
    try:
        target_price = float(target_text)
    except ValueError:
        errors.append("Target price must be a number.")

    if len(errors) == 0:
        errors = tracker.add_product(url, target_price)

    if len(errors) == 0:
        print("Product added and first price saved!")
    else:
        for error in errors:
            print("Error: " + error)


def remove_product():
    show_products()
    id_text = input("Enter the ID to remove: ")
    if id_text.isdigit():
        tracker.db.remove_product(int(id_text))
        print("Removed (if that ID existed).")
    else:
        print("Error: please enter a number.")


def show_history():
    show_products()
    id_text = input("Enter the ID to view: ")
    if id_text.isdigit():
        history = tracker.db.get_price_history(int(id_text))
        if len(history) == 0:
            print("No history found for that ID.")
        else:
            for row in history:
                print(row["checked_at"] + "  ->  " + str(row["price"]) + "  (" + row["availability"] + ")")
    else:
        print("Error: please enter a number.")


def show_alerts():
    alerts = tracker.db.get_alerts()
    if len(alerts) == 0:
        print("No alerts yet.")
    else:
        for alert in alerts:
            print(alert["time"] + " | " + alert["product"][:40] + " | " + alert["message"])


def ask_yes_no(prompt):
    while True:
        answer = input(prompt + " (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please type y or n.")


def list_groups():
    groups = tracker.db.get_all_groups()
    if len(groups) == 0:
        print("No comparison groups yet.")
    else:
        for group in groups:
            count = len(tracker.db.get_group_products(group["id"]))
            print(str(group["id"]) + ". " + group["name"] + "  (" + str(count) + " site(s))")
    return groups


def add_listing():
    list_groups()
    name = input("Group name (an existing one, or a new name like 'Sony WH-1000XM5'): ").strip()
    if name == "":
        print("Error: the group name cannot be empty.")
        return
    group = tracker.db.get_group_by_name(name)
    if group is None:
        group_id = tracker.db.add_group(name)
        print("Created new group '" + name + "'.")
    else:
        group_id = group["id"]

    while True:
        url = input("Product URL on one site: ")
        target_text = input("Target price: ")
        try:
            target_price = float(target_text)
        except ValueError:
            print("Error: target price must be a number.")
            target_price = None

        if target_price is not None:
            errors = tracker.add_product(url, target_price, group_id)
            if len(errors) == 0:
                print("Added " + site_name(url.strip()) + " to '" + name + "'.")
            else:
                for error in errors:
                    print("Error: " + error)

        if not ask_yes_no("Add another site to this group?"):
            break


def show_comparison():
    groups = list_groups()
    if len(groups) == 0:
        return
    id_text = input("Enter the group ID to compare: ")
    if not id_text.isdigit():
        print("Error: please enter a number.")
        return
    group_id = int(id_text)
    group = None
    for item in groups:
        if item["id"] == group_id:
            group = item
    if group is None:
        print("No group with that ID.")
        return

    if ask_yes_no("Refresh prices from the websites first?"):
        tracker.check_group(group_id)

    result = tracker.compare_group(group_id)
    if len(result["listings"]) == 0:
        print("This group has no sites yet. Use 'Add a site' first.")
        return

    print("\n=== " + group["name"] + " ===")
    for number, item in enumerate(result["listings"], start=1):
        price_text = "no price"
        if item["price"] is not None:
            price_text = str(item["price"])
        line = str(number) + ". " + item["site"].ljust(22) + price_text.ljust(12) + item["availability"]
        if result["cheapest"] is not None and item["id"] == result["cheapest"]["id"]:
            line = line + "   <-- CHEAPEST NOW"
        print(line)
        print("   " + item["url"])

    if result["cheapest"] is None:
        print("\nNo in-stock listing with a price right now.")
    if result["lowest_ever"] is not None:
        best = result["lowest_ever"]
        print("\nLowest price ever recorded across all sites: " + str(best["price"])
              + " on " + site_name(best["url"]) + " (" + best["checked_at"] + ")")
    print("Note: prices are compared as plain numbers - keep all sites in the same currency.")


def delete_group():
    groups = list_groups()
    if len(groups) == 0:
        return
    id_text = input("Enter the group ID to delete: ")
    if id_text.isdigit():
        tracker.db.remove_group(int(id_text))
        print("Group deleted (its sites are still tracked as single products).")
    else:
        print("Error: please enter a number.")


def compare_menu():
    while True:
        print("\n--- Compare prices across sites ---")
        print("1. Add a site to a comparison group")
        print("2. Show a comparison")
        print("3. Delete a group")
        print("4. Back")
        choice = input("Choose an option: ").strip()
        if choice == "1":
            add_listing()
        elif choice == "2":
            show_comparison()
        elif choice == "3":
            delete_group()
        elif choice == "4":
            break
        else:
            print("Invalid choice, try again.")


def main():
    email_setup.startup_email()
    while True:
        show_menu()
        choice = input("Choose an option: ").strip()
        if choice == "1":
            add_product()
        elif choice == "2":
            remove_product()
        elif choice == "3":
            show_products()
        elif choice == "4":
            show_history()
        elif choice == "5":
            count = tracker.check_all()
            print("Checked " + str(count) + " product(s).")
        elif choice == "6":
            tracker.run_scheduler()
        elif choice == "7":
            show_alerts()
        elif choice == "8":
            email_setup.setup_email()
        elif choice == "9":
            compare_menu()
        elif choice == "10":
            print("Bye!")
            break
        else:
            print("Invalid choice, try again.")


if __name__ == "__main__":
    main()