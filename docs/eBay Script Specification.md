# **Technical Specification: eBay Draft CSV Generator (v2)**

## **1\. Objective**

Create a Python script that pulls enriched DVD product data from a local SQLite database and formats it into the official eBay Draft Listing Template. The output must be a CSV file that preserves eBay's mandatory \#INFO metadata headers.

## **2\. Input Requirements**

1. **Source Database**: /Users/blickt/Documents/src/ebay\_seller\_port/data/dvd\_catalog.db  
   * **Instruction for Coding Agent**: Inspect the database schema and existing database handling code in the repository to determine the correct table names and columns (e.g., upc, epid, title, image\_url).  
2. **Target Template (eBay-draft-listing-template.csv)**: The official eBay CSV provided in the project root, which starts with \#INFO metadata rows.

## **3\. Configuration Variables (.env)**

The script must use python-dotenv to load configurations. Following existing project patterns, the .env file should include:

* SKU\_PREFIX: Prefix for the custom label (e.g., E-0313-).  
* START\_COUNT: The integer to start the SKU sequence (e.g., 1).  
* EBAY\_CATEGORY\_ID: Default to 617 (DVDs).  
* EBAY\_CONDITION\_ID: Default to NEW.  
* EBAY\_DESCRIPTION\_TEMPLATE: A string for the listing description.  
* DATABASE\_PATH: Full path to the .db file.

## **4\. Logical Transformation Rules**

For every record fetched from the database, create a row in the output CSV mapped as follows:

| Target Template Column | Database / Logic Source |
| :---- | :---- |
| **Action** | Constant: Draft |
| **Custom label (SKU)** | SKU\_PREFIX \+ str(START\_COUNT \+ index).zfill(3) |
| **Category ID** | From .env (Default 617\) |
| **Title** | title from database |
| **UPC** | upc from database |
| **Price** | **Leave Empty** (User will manually price via eBay app) |
| **Quantity** | Constant: 1 |
| **Item photo URL** | image\_url (or equivalent) from database |
| **Condition ID** | From .env (Default NEW) |
| **Description** | From .env |
| **Format** | Constant: FixedPrice |

## **5\. File Handling & Standards**

1. **Preserve Metadata**: The script must read the first 4-5 rows of the eBay-draft-listing-template.csv that start with \#INFO and prepend them to the output file before writing headers/data.  
2. **Existing Code Integration**: The coding agent should reuse existing database connection classes/functions found in the ebay\_seller\_port project to maintain consistency.  
3. **Encoding**: Output must be UTF-8 with newline='' to ensure compatibility with eBay's uploader and different OS line endings.

## **6\. Expected Output**

A file named ebay\_upload\_ready.csv ready for bulk upload via **eBay Seller Hub \> Reports \> Uploads**.