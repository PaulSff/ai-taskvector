# NdcXmlToJson Unit

This Unit converts NDC XML messages (IATA) into JSON equivalents.

It uses the `singletons-\*.json` supporting files in order to ouput valid NDC messages (elements with maxOccurs > 1 should always be in arrays, whatever the number of actual occurences). This file is stored in the `singletons` folder: the correct NDC version should be chosen for the input message version.

**Inputs**
..

**Outputs**
..

**Params**
 Params: singleton_file | str

**Assumption**: input XML is well-formed and the first element is the root.

**References**: https://github.com/airtechzone/ndc-xml2json-js/tree/master/singletons
