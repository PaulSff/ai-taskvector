# NdcXmlToJson Unit

This Unit converts NDC XML messages (IATA) into JSON equivalents.

It uses the `singletons-\*.json` supporting files in order to ouput valid NDC messages (elements with maxOccurs > 1 should always be in arrays, whatever the number of actual occurences). This file is stored in the `singletons` folder: the correct NDC version should be chosen for the input message version.

**Inputs**
- `data` (str): The NDC XML string to be converted.

**Outputs**
- `json` (dict): The converted NDC message in JSON format.
- `error` (str): Error message if the conversion fails, otherwise an empty string.

**Params**
- `singleton_file` (str): Path to the JSON singleton definition file (e.g., `singletons-172.json`). This file ensures that elements with `maxOccurs > 1` are always represented as arrays in the output, regardless of the number of occurrences in the specific XML input.

**Assumption**: Input XML is well-formed and the first element is the root.

### Example

**Input XML**:
```xml
<AirShoppingRQ xmlns="http://www.iata.org/IATA/EDIST/2017.2" Version="17.2">
	<CoreQuery>
    <OriginDestinations>
      <OriginDestination>
        <Departure>
          <AirportCode>MOW</AirportCode>
          <Date>2026-10-09</Date>
        </Departure>
        <Arrival>
          <AirportCode>LED</AirportCode>
        </Arrival>
      </OriginDestination>
   </OriginDestinations>
	</CoreQuery>
</AirShoppingRQ>
```

**Output JSON**:
```json
{
  "AirShoppingRQ": {
    "$": {
      "Version": "17.2"
    },
    "CoreQuery": {
      "OriginDestinations": {
        "OriginDestination": [
          {
            "Departure": {
              "AirportCode": { "_": "MOW" },
              "Date": { "_": "2026-10-09" }
            },
            "Arrival": {
              "AirportCode": { "_": "LED" }
            }
          }
        ]
      }
    }
  }
}
```

**References**: [ndc-xml2json-js](https://github.com/airtechzone/ndc-xml2json-js/tree/master/singletons)
