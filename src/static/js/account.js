async function UploadSignature(escaped_user) {
  const elem = document.getElementById("signature");
  if (elem.files.length === 0) {
    alert("No file selected!");
    return;
  }
  const formData = new FormData();
  formData.append("sig", elem.files[0]);
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), 5000);
  let reload = false;
  try {
    const response = await AppFetch('/upload/signature/' + escaped_user,
      {method: "POST", body: formData, signal: ctrl.signal});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message || "Failed uploading signature.", response.status);
    } else {
      if (response.status === 206) {
        alert(await response.text());
      }
      reload = true;
    }
  } catch (error) {
    console.error("Failed uploading signature:", error);
    OpenErrorModal();
  } finally {
    clearTimeout(timeout);
  }
  if (reload) window.location.reload();
}

async function DeleteSignature(escaped_user) {
  let reload = false;
  try {
    const response = await AppFetch("/delete/signature/" + escaped_user,
      {method: "POST", body: new FormData()});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message || "Failed deleting signature.", response.status);
    } else {
      reload = true;
    }
  } catch (error) {
    console.error("Failed deleting signature:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

async function ChangeUsername(email, user) {
  let reload = false;
  try {
    const response = await AppFetch("/account/" + email + "/update/username/" + user,
      {method: "POST", body: new FormData()});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message || "Failed changing username.", response.status);
    } else {
      reload = true;
    }
  } catch (error) {
    console.error("Failed changing username:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

async function DeleteAccount(email, logout) {
  const query = logout ? "?logout=True" : "";
  let reload = false;
  try {
    const response = await AppFetch("/account/" + email + "/delete" + query,
      {method: "POST", body: new FormData()});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message || "Failed deleting account.", response.status);
    } else {
      reload = true;
    }
  } catch (error) {
    console.error("Failed deleting account:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

async function SetAdmin(email, checked) {
  const query = checked ? "?admin=True" : "";
  try {
    const response = await AppFetch("/account/" + email + "/set_admin" + query,
      {method: "POST", body: new FormData()});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message || "Failed changing admin status.", response.status);
    } else {
      alert(email + " changed to " + (checked ? " admin " : "no-admin"));
    }
  } catch (error) {
    console.error("Failed changing admin status:", error);
    OpenErrorModal();
  }
}

async function UpdateUsername() {
  const formData = new FormData();
  formData.append("old_username", document.getElementById("old_username").value);
  formData.append("new_username", document.getElementById("new_username").value);
  try {
    const response = await AppFetch("/user_management/update_username",
      {method: "POST", body: formData});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message || "Failed updating username.", response.status);
    } else {
      alert("username successfully changed!");
    }
  } catch (error) {
    console.error("Failed updating username:", error);
    OpenErrorModal();
  }
}

async function DeleteVerificationKey(email) {
  let reload = false;
  try {
    const response = await AppFetch("/user_management/delete_key/" + email, {method: "POST"});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message || "Failed deleting verification key.", response.status);
    } else {
      alert("Verification key for " + email + " successfully deleted!");
      reload = true;
    }
  } catch (error) {
    console.error("Failed deleting verification key:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}
