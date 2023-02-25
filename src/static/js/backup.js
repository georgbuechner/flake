function AddBackup() {
  fetch("/settings/backups/add", {method: "POST"})
    .then(response => {
      if (!response.ok) 
        response.text().then(text => OpenErrorModal(text, response.status));
      else 
        window.location=window.location;
    }) 
    .catch(error => OpenErrorModal(error, 500));
}

function DeleteBackup(backup) {
  fetch("/settings/backups/delete/"+backup, {method: "POST"})
    .then(response => {
      if (!response.ok) 
        response.text().then(text => OpenErrorModal(text, response.status));
      else 
        window.location=window.location;
    }) 
    .catch(error => OpenErrorModal(error, 500));
}

function LoadBackup(backup) {
  fetch("/settings/backups/load/"+backup, {method: "POST"})
    .then(response => {
      if (!response.ok) 
        response.text().then(text => OpenErrorModal(text, response.status));
      else 
        window.location=window.location;
    }) 
    .catch(error => OpenErrorModal(error, 500));
}
