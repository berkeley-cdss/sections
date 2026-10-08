import Button from "react-bootstrap/Button";
import Modal from "react-bootstrap/Modal";
import FormControl from "react-bootstrap/FormControl";
import { useContext, useState } from "react";
import type { Section } from "./models";
import StateContext from "./StateContext";

type Props = {
  show: boolean;
  section: Section;
  onClose: () => void;
  onSubmit: (enrollmentCode: string) => void;
};

export default function ConfirmEnrollmentModal({
  show,
  section,
  onClose,
  onSubmit,
}: Props) {
  const { config } = useContext(StateContext);
  const [enrollmentCode, setEnrollmentCode] = useState("");

  return (
    <Modal show={show} onHide={() => onClose()}>
      <Modal.Header closeButton>
        <Modal.Title>Confirm Join</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {((section.name === "Lab" && !config.canStudentsChangeLab) ||
          (section.name === "Discussion" && !config.canStudentsChangeDiscussion) ||
          (section.name === "Tutoring" && !config.canStudentsChangeTutoring)) &&
          "Warning! After you join this section, you will not be" +
            " able to change your preference."}
        {section.needsEnrollmentCode && (
          <FormControl
            value={enrollmentCode ?? ""}
            onChange={(e) => setEnrollmentCode(e.target.value)}
          />
        )}
      </Modal.Body>
      <Modal.Footer>
        <Button
          variant="success"
          onClick={() => {
            onSubmit(enrollmentCode);
            onClose();
          }}
        >
          Submit
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
