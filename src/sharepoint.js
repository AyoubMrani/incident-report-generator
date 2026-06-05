import spauth from "node-sp-auth";
import fetch from "node-fetch";
import fs from "fs";
import ConfigParser from "configparser";  // ✅ default import

class SharePoint {

  static async uploadToRadia(fileName, reportDestination, typeIssues) {

    const parser = new ConfigParser();
    parser.read("resources/configuracion.properties");  // ✅ double-s

    const siteUrl    = parser.get("SharePoint", "site");
    const folderPath = parser.get("SharePoint", "folder_path");
    const username   = parser.get("SharePoint", "user");
    const password   = parser.get("SharePoint", "password");

    const { headers } = await spauth.getAuth(siteUrl, { username, password });

    const fileContent    = fs.readFileSync(reportDestination);
    const fullFolderPath = `${folderPath}/${typeIssues}`;

    const uploadUrl = `${siteUrl}/_api/web/GetFolderByServerRelativeUrl('${encodeURIComponent(fullFolderPath)}')/Files/add(url='${encodeURIComponent(fileName)}',overwrite=true)`;

    const response = await fetch(uploadUrl, {
      method: "POST",
      headers: {
        ...headers,
        "Content-Length": fileContent.length,
        Accept: "application/json;odata=verbose",
      },
      body: fileContent,
    });

    if (!response.ok) {
      const err = await response.text();
      throw new Error(`Upload failed (${response.status}): ${err}`);
    }

    console.log(`File '${fileName}' successfully uploaded to '${fullFolderPath}'.`);
  }
}

export default SharePoint;