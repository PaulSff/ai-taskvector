## NdcJsonToXml

This Unit converts NDC JSON messages into XML equivalents.

It uses the `sequences-*.json` supporting files in order to output valid NDC messages (with properly ordered sequences). This file is stored in the sequences folder: the correct NDC version should be chosen for the input message version.

**Implementation Note:** This unit uses a recursive approach to build the XML tree. It supports attributes (via the `$` key) and text content (via the `_` key) within the input JSON structure.

**Inputs**
- `data` (JsonValue): The NDC JSON object to be converted. The JSON must contain exactly one root element.

**Outputs**
- `xml` (str): The resulting NDC XML string.
- `error` (str): Error message if the conversion fails, otherwise an empty string.

**Params**
 Params: sequence_file | str (path to the `sequences-*.json`)


**References**: https://github.com/airtechzone/ndc-json2xml-js/tree/master/sequences

## Usage Example

### Input JSON
```json
{
  "AirShoppingRQ": {
    "$": { "version": "17.2" },
    "Party": {
      "Sender": { "$": { "Role": "NDC-Aggregator" } }
    }
  }
}
```

### Output XML
```xml
<AirShoppingRQ version="17.2">
  <Party>
    <Sender Role="NDC-Aggregator"/>
  </Party>
</AirShoppingRQ>
```

## Running Tests

To verify the unit's functionality, run the provided test suite using the following command:

```bash
pytest /Users/jm/ai-taskvector/units/travel/json2ndc_xml/test_json2ndc_xml.py
```
