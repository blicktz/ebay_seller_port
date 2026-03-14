# **Technical Specification: eBay Category Template Generator (v4)**

## **1\. Objective**

Generate a CSV using the "fx\_category\_template\_EBAY\_US" format to create pre-filled, scheduled listings that act as advanced drafts.

## **2\. Environment Variables (.env)**

The following keys are required in the .env file:

* SKU\_PREFIX: (e.g., "E-0313-")  
* START\_COUNT: (e.g., 1\)  
* SCHEDULE\_DAYS\_AHEAD: 21 (Integer)  
* PLACEHOLDER\_PRICE: 99.99  
* SHIPPING\_POLICY: "Single DVD/VHS \-Free Shipping"  
* PAYMENT\_POLICY: "eBay Managed Payments (281844116014)"  
* RETURN\_POLICY: "Free return within 30d"  
* POSTAL\_CODE: "94043"  
* REGION\_CODE: "DVD: 1 (US, Canada...)"

## **3\. Database Mapping**

Map the following fields from the dvd\_catalog.db:

* UPC \-\> UPC  
* Title \-\> \*Title  
* Primary Image URL \-\> PicURL

## **4\. Logical Transformation Rules**

The output CSV must contain these columns (headers must match the new template exactly):

| Template Header (Exact) | Value / Logic |
| :---- | :---- |
| **\*Action(...)** | Add |
| **CustomLabel** | SKU\_PREFIX \+ str(START\_COUNT \+ index).zfill(3) |
| **\*Category** | 617 |
| **\*Title** | Title from DB |
| **ScheduleTime** | Current Time \+ SCHEDULE\_DAYS\_AHEAD (Format: YYYY-MM-DD HH:MM:SS) |
| **\*ConditionID** | 1000 |
| **\*C:Format** | DVD |
| **C:Region Code** | REGION\_CODE from .env |
| **UPC** | UPC from DB |
| **PicURL** | image\_url from DB |
| **\*Description** | Placeholder: "Brand New and Sealed DVD." |
| **\*Format** | FixedPrice |
| **\*Duration** | GTC |
| **\*StartPrice** | PLACEHOLDER\_PRICE from .env |
| **\*Quantity** | 1 |
| **\*Location** | POSTAL\_CODE from .env |
| **ShippingProfileName** | SHIPPING\_POLICY from .env |
| **PaymentProfileName** | PAYMENT\_POLICY from .env |
| **ReturnProfileName** | RETURN\_POLICY from .env |

## **5\. Metadata Handling**

* **Row 1**: Must be exactly Info,Version=1.0.0,Template=fx\_category\_template\_EBAY\_US  
* **Row 2**: Is the Header Row (starts with \*Action...)  
* Do NOT include the \#INFO rows from previous templates; this specific template uses the Info,Version... format on Line 1\.

## **6\. Dimensions & Weight**

Since you are using ShippingProfileName, you do NOT need to provide weight/dimensions in the CSV. eBay will pull those from the "Single DVD/VHS \-Free Shipping" policy automatically.

*(If your policy is set to "Calculated", ensure the policy itself has a default weight saved inside eBay Seller Hub).*