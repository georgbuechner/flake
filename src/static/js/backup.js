async function AddBackup() {
  let reload = false;
  try {
    const response = await fetch("/settings/backups/add", {method: "POST"});
    const message = await response.text();

    if (!response.ok) {
      OpenErrorModal(message || "Adding backup failed.", response.status);
    } else {
      reload = true;
    }
  } catch (error) {
    console.error("Failed adding backup:", error); 
    OpenErrorModal("The result could not be confirmed. The backup may already have been created. " +
      "Reload and check before retrying.", 500);
  }
  if (reload) {
    window.location.reload();
  }
}

async function DeleteBackup(backup) {
  let reload = false 

  try {
    const response = await fetch(
      "/settings/backups/delete/" + encodeURIComponent(backup), 
      {method: "POST"}
    );
    const message = await response.text();
    if (!response.ok) {
      OpenErrorModal(message || "Deleting backup failed.", response.status);
    } else {
      reload = true;
    }
  } catch (error) {
    console.error("Failed deleting backup:", error); 
    OpenErrorModal("The result could not be confirmed. The backup may already have been deleted. " +
      "Reload and check before retrying.", 500);
  }
  if (reload) {
    window.location.reload();
  }
}

async function LoadBackup(backup) {
  let reload = false;

  try {
    const response = await fetch(
      "/settings/backups/load/" + encodeURIComponent(backup), 
      {method: "POST"}
    );
    const message = await response.text(); 

    if (!response.ok) {
      OpenErrorModal(message || "Loading backup failed.", response.status);
    } else {
      reload = true;
    }
  } catch(error) {
    console.error("Failed loading backup:", error); 
    OpenErrorModal("The result could not be confirmed. The backup may already have been loaded. " +
      "Reload and check before retrying.", 500);
  }
  if (reload) {
    window.location.reload();
  }
}

async function DownloadBackup(backup) {
  let url;
  let link; 
  try {
    const response = await fetch(
      "/settings/backups/download/" + encodeURIComponent(backup), 
      {method: "POST"}
    );

    if (!response.ok) {
      const message = await response.text(); 
      OpenErrorModal(message || "Downloading backup failed", response.status);
      return;
    }
    const blob = await response.blob()
    url = window.URL.createObjectURL(blob);
    link = document.createElement("a");
    link.style.display = "none";
    link.href = url;
    link.download = backup;
    document.body.appendChild(link);
    link.click();
  } catch (error) {
    console.error("Failed downloading backup:", error);
    OpenErrorModal("The backup could not be downloaded. Please try again.", 500);
  } finally {
    // Allow the browser to start the download before releasing its URL. 
    if (url) {
      setTimeout(() => {
        window.URL.revokeObjectURL(url);
        if (link) link.remove();
      }, 100);
    }
  }
}
